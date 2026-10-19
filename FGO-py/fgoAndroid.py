import os,re,shutil,struct,threading,time,cv2,numpy
from collections import deque
from functools import partial
from airtest import aircv
from airtest.core.android.adb import ADB
from airtest.core.android.android import Android as Airtest
from airtest.core.android.constant import CAP_METHOD
from airtest.core.android.cap_methods.adbcap import AdbCap
from airtest.core.android.cap_methods.screen_proxy import ScreenProxy
from airtest.core.android.rotation import RotationWatcher
from fgoConst import KEYMAP
from fgoLogging import getLogger
from fgoSchedule import schedule,ScriptStop
logger=getLogger('Android')

if adb:=shutil.which('adb'):
    logger.warning(f'Using Adb in PATH: {adb}')
    ADB.builtin_adb_path=staticmethod(lambda:adb)

class Android(Airtest):
    JAVACAP_INVALID_LIMIT=3
    ADB_CAPTURE_TIMEOUT=5
    ADB_RECOVERY_SECONDS=30
    ADB_RECOVERY_ATTEMPTS=60
    ADB_HEALTH_WINDOW=60
    ADB_HEALTH_FAILURE_LIMIT=45
    ADB_WARNING_INTERVAL=10
    ADB_STABLE_FRAMES=5
    ADB_STABLE_ATTEMPTS=30
    ADB_STABLE_INTERVAL=1
    ADB_RECONNECT_LIMIT=2
    ADB_RECONNECT_WINDOW=600
    ADB_CAPTURE_MODES=('exec-png','shell-png','exec-raw')
    def __init__(self,serial=None,**kwargs):
        self.mutex=threading.Lock()
        self.captureMutex=threading.Lock()
        self.invalidFrame=0
        self.adbCaptureMode='exec-png'
        self.adbCaptureHealth=deque(maxlen=self.ADB_HEALTH_WINDOW)
        self.captureFailure=None
        self.captureWarningAt=float('-inf')
        self.adbReconnectTimes=deque()
        self.captureGeneration=0
        if serial is None or serial=='None':
            self.name=None
            return
        try:
            super().__init__(serial,**{'cap_method':CAP_METHOD.JAVACAP,'host':os.environ.get('ADB_SERVER_SOCKET','tcp:localhost:5037').split(":")[1:]}|kwargs)
            self.package=next(i for i in re.findall(r'ACTIVITY ([A-Za-z0-9_.]+)/',self.adb.shell('dumpsys activity top'))[::-1]if(lambda x:x[2]-x[0]>959 and x[3]-x[1]>539)(self.get_render_resolution(True,i)))
            self.adjustOffset()
            self.rotation_watcher.reg_callback(lambda _:self.adjustOffset())
        except Exception as e:
            logger.exception(e)
            self.name=None
        else:self.name=self.serialno
    @property
    def available(self):
        if not self.name or self.captureFailure:return False
        if self.touch_proxy.server_proc.poll()is None:return True # Only compatible with minitouch & maxtouch
        self.name=None
        return False
    @staticmethod
    def enumDevices():return[i for i,_ in ADB().devices('device')]
    def adjustOffset(self):
        self.render=[round(i)for i in self.get_render_resolution(True,self.package)]
        self.scale,self.border=(720/self.render[3],(round(self.render[2]-self.render[3]*16/9)>>1,0))if self.render[2]*9>self.render[3]*16 else(1280/self.render[2],(0,round(self.render[3]-self.render[2]*9/16)>>1))
        self.key={c:[round(p[i]/self.scale+self.border[i]+self.render[i])for i in range(2)]for c,p in KEYMAP.items()}
    def touch(self,pos):
        with self.mutex:
            self._checkCaptureFailure()
            super().touch([round(pos[i]/self.scale+self.border[i]+self.render[i])for i in range(2)])
    def swipe(self,begin,end):
        p1,p2=[numpy.array(self._touch_point_by_orientation([i[j]/self.scale+self.border[j]+self.render[j]for j in range(2)]))for i in(begin,end)]
        vd=p2-p1
        lvd=numpy.linalg.norm(vd)
        vd/=.2*self.scale*lvd
        vx=numpy.array([0.,0.])
        def send(method,pos):self.touch_proxy.handle(' '.join((method,'0',*[str(i)for i in self.touch_proxy.transform_xy(*pos)],'50\nc\n')))
        with self.mutex:
            self._checkCaptureFailure()
            send('d',p1)
            time.sleep(.01)
            for _ in range(2):
                send('m',p1+vx)
                vx+=vd
                time.sleep(.02)
            vd*=5
            while numpy.linalg.norm(vx)<lvd:
                send('m',p1+vx)
                vx+=vd
                time.sleep(.008)
            send('m',p2)
            time.sleep(.35)
            self.touch_proxy.handle('u 0\nc\n')
            time.sleep(.02)
    def press(self,key):
        with self.mutex:
            self._checkCaptureFailure()
            super().touch(self.key[key])
    def pinch(self):
        with self.mutex:
            self._checkCaptureFailure()
            super().pinch(percent=.2)
    def _checkCaptureFailure(self):
        if self.captureFailure:raise RuntimeError(self.captureFailure)
    @staticmethod
    def _isInvalidCaptureFrame(frame):
        if frame is None or not frame.size or not numpy.any(frame):return True
        # A broken JAVACAP JPEG can decode successfully as an almost entirely
        # white image with a solid black rectangle, so it must not reach the
        # image detector merely because it contains a few non-zero pixels.
        return numpy.mean(numpy.all(frame>250,axis=2))>.9
    def _useCaptureMethod(self,method):
        if method==CAP_METHOD.ADBCAP:
            # Airtest's setter probes ADB without a timeout and may silently
            # select JAVACAP again. Install the selected backend explicitly.
            if self._screen_proxy:self._screen_proxy.teardown_stream()
            self._screen_proxy=ScreenProxy(AdbCap(self.adb))
        else:self.screen_proxy=method
        self.invalidFrame=0
        logger.warning(f'Screen capture switched to {self.screen_proxy.method_name}')
    def _fallBackToAdbcap(self):
        # Keep the fallback for this connection. Switching capture sources can
        # change portrait pixels and be mistaken for servant replacement,
        # causing the skill dispatcher to use the reserve servants' settings.
        self._useCaptureMethod(CAP_METHOD.ADBCAP)
        logger.warning('Keeping ADBCAP until reconnect to preserve battle image comparisons')
    def _cropScreenshot(self,frame):
        if frame is None:raise RuntimeError('Screen capture returned no frame')
        cropped=frame[self.render[1]+self.border[1]:self.render[1]+self.render[3]-self.border[1],self.render[0]+self.border[0]:self.render[0]+self.render[2]-self.border[0]]
        if not cropped.size:raise RuntimeError(f'Invalid screen capture size: {frame.shape}')
        return cv2.resize(cropped,(1280,720),interpolation=cv2.INTER_CUBIC)
    @staticmethod
    def _decodeRawScreenshot(data,headerSize=16):
        # Android screencap: width, height, pixel format, optional dataspace,
        # then tightly packed pixels. Reject partial/unknown layouts.
        if headerSize not in(12,16)or len(data)<headerSize:raise RuntimeError('Truncated raw screenshot header')
        width,height,fmt=struct.unpack_from('<III',data)
        channels={1:4,2:4,3:3,5:4}.get(fmt)
        if not channels or not(0<width<=16384 and 0<height<=16384):
            raise RuntimeError(f'Unsupported raw screenshot: {width}x{height}, format {fmt}')
        # Do not infer the header size from payload length: losing four bytes
        # from a modern frame must not turn it into a shifted legacy frame.
        if len(data)!=headerSize+width*height*channels:raise RuntimeError('Truncated or unsupported raw screenshot pixels')
        pixels=numpy.frombuffer(data,dtype=numpy.uint8,offset=headerSize).reshape(height,width,channels)
        return pixels[:,:,:3].copy()if fmt==5 else cv2.cvtColor(pixels,cv2.COLOR_RGBA2BGR if channels==4 else cv2.COLOR_RGB2BGR)
    def _readAdbScreenshot(self,mode,timeout):
        command=['shell'if mode=='shell-png'else'exec-out','screencap']
        if self.adb.display_id is not None:command+=['-d',str(self.adb.display_id)]
        if mode!='exec-raw':command+=['-p']
        data=self.adb.cmd(command,ensure_unicode=False,timeout=timeout)
        if mode=='exec-raw':frame=self._decodeRawScreenshot(data,16 if self.adb.sdk_version>=26 else 12)
        else:
            # exec-out is binary-safe: never rewrite newline bytes in its PNG.
            if mode=='shell-png':data=data.replace(self.adb.line_breaker,b'\n')
            frame=cv2.imdecode(numpy.frombuffer(data,dtype=numpy.uint8),cv2.IMREAD_COLOR)if data else None
        if frame is not None and self.adb.sdk_version<=24:
            frame=aircv.rotate(frame,self.adb.display_info['orientation']*90,clockwise=False)
        return frame
    def _screenshotAdb(self):
        if self.captureFailure:raise RuntimeError(self.captureFailure)
        deadline=time.monotonic()+self.ADB_RECOVERY_SECONDS
        start=self.ADB_CAPTURE_MODES.index(self.adbCaptureMode)
        lastFrame=None
        reason='No frame'
        for attempt in range(self.ADB_RECOVERY_ATTEMPTS):
            schedule.checkStop()
            now=time.monotonic()
            remaining=deadline-now
            if remaining<=0:break
            mode=self.ADB_CAPTURE_MODES[(start+attempt//3)%len(self.ADB_CAPTURE_MODES)]
            try:
                frame=self._readAdbScreenshot(mode,min(self.ADB_CAPTURE_TIMEOUT,remaining))
                schedule.checkStop()
                if frame is None or not frame.size:raise RuntimeError('Empty or undecodable screenshot')
                frame=self._cropScreenshot(frame)
                lastFrame=frame
                if self._isInvalidCaptureFrame(frame):raise RuntimeError('Black or nearly white screenshot')
            except ScriptStop:raise
            except Exception as e:
                reason=f'{type(e).__name__}: {str(e)[:300]}'
                self.adbCaptureHealth.append(True)
                logger.debug(f'ADBCAP {mode} attempt {attempt+1} failed: {reason}')
                if now-self.captureWarningAt>=self.ADB_WARNING_INTERVAL:
                    logger.warning(f'ADBCAP screenshot unavailable; bounded recovery in progress ({mode}): {reason}')
                    self.captureWarningAt=now
            else:
                self.adbCaptureHealth.append(False)
                if not self._adbCaptureUnhealthy():
                    if attempt or mode!=self.adbCaptureMode:
                        logger.debug(f'ADBCAP recovered using {mode} after {attempt+1} attempt(s)')
                    self.adbCaptureMode=mode
                    return frame
            # One good image must not erase a sustained failure pattern across
            # screenshot() calls. A persistently broken source is stopped even
            # when it occasionally returns a usable frame before each deadline.
            if self._adbCaptureUnhealthy():
                reason=f'Persistent capture failure: {sum(self.adbCaptureHealth)}/{len(self.adbCaptureHealth)} recent captures failed; last issue: {reason}'
                break
            remaining=deadline-time.monotonic()
            if attempt+1<self.ADB_RECOVERY_ATTEMPTS and remaining>0:schedule.sleep(min(.5,remaining))
        # Do not let invalid frames consume the recognition fuse or trigger
        # battle actions. Preserve a separate capture diagnostic instead.
        path=time.strftime('fgoLog/CaptureFailure_%Y-%m-%d_%H.%M.%S.png')
        if lastFrame is not None:
            try:
                if cv2.imwrite(path,lastFrame):logger.error(f'Failed capture saved to {path}')
            except Exception as e:logger.warning(f'Could not save failed capture: {e}')
        self.captureFailure=f'ADBCAP recovery exhausted; emulator screenshot unavailable: {reason}. Capture disabled until device reconnect.'
        raise RuntimeError(self.captureFailure)
    def _adbCaptureUnhealthy(self):
        return len(self.adbCaptureHealth)==self.ADB_HEALTH_WINDOW and sum(self.adbCaptureHealth)>=self.ADB_HEALTH_FAILURE_LIMIT
    def _reconnectAdb(self,restartServer=False):
        # Called only while captureMutex and the input mutex are held. Replace
        # dead transport helpers, not the Android/Device or battle objects.
        originalCmd=self.adb.cmd
        self.adb.cmd=partial(originalCmd,timeout=self.ADB_CAPTURE_TIMEOUT)
        try:
            schedule.checkStop()
            oldWatcher=getattr(self,'rotation_watcher',None)
            if oldWatcher:
                oldWatcher.teardown()
                thread=getattr(oldWatcher,'_t',None)
                if thread and thread.is_alive():
                    thread.join(timeout=self.ADB_CAPTURE_TIMEOUT+1)
                    if thread.is_alive():raise RuntimeError('Old rotation watcher did not stop')
            oldTouch=getattr(self,'_touch_proxy',None)
            self._touch_proxy=None
            if oldTouch:
                try:oldTouch.teardown()
                except Exception as e:logger.warning(f'Old touch connection cleanup failed: {e}')
            oldScreen=getattr(self,'_screen_proxy',None)
            self._screen_proxy=None
            if oldScreen:
                try:oldScreen.teardown_stream()
                except Exception as e:logger.warning(f'Old capture connection cleanup failed: {e}')
            serial=self.adb.serialno
            if restartServer:
                self.adb.cmd(['kill-server'],device=False,timeout=10)
                # Complete the restart even if Stop was pressed during kill;
                # check cancellation before rebuilding helpers or resuming.
                self.adb.cmd(['start-server'],device=False,timeout=10)
                schedule.checkStop()
            if ':'in serial:
                # Stage one affects only this endpoint. Stage two explicitly
                # restarts the configured shared server before reconnecting.
                if not restartServer:self.adb.cmd(['disconnect',serial],device=False)
                schedule.checkStop()
                self.adb.cmd(['connect',serial],device=False)
            elif not restartServer:self.adb.cmd(['reconnect'])
            self.adb.cmd(['wait-for-device'])
            if self.adb.cmd(['get-state']).strip()!='device':raise RuntimeError('ADB did not become ready')
            schedule.checkStop()
            self.rotation_watcher=RotationWatcher(self.adb,self.ori_method)
            self._register_rotation_watcher()
            self._current_orientation=None
            self._display_info={}
            self.adjustOffset()
            self.rotation_watcher.reg_callback(lambda _:self.adjustOffset())
            # Establish input transport without replaying any tap/swipe.
            if self.touch_proxy.method_name not in('MINITOUCH','MAXTOUCH'):
                raise RuntimeError('Touch transport could not be restored')
            self._screen_proxy=ScreenProxy(AdbCap(self.adb))
        finally:self.adb.cmd=originalCmd
    def _waitForStableAdbCapture(self):
        # Probe actual frames directly: _screenshotAdb hides failed reads behind
        # retries, which would incorrectly count intermittent success as stable.
        deadline=time.monotonic()+self.ADB_RECOVERY_SECONDS
        consecutive=0
        reason='No frame'
        for attempt in range(self.ADB_STABLE_ATTEMPTS):
            schedule.checkStop()
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            try:
                frame=self._cropScreenshot(self._readAdbScreenshot(self.adbCaptureMode,min(self.ADB_CAPTURE_TIMEOUT,remaining)))
                schedule.checkStop()
                if self._isInvalidCaptureFrame(frame):raise RuntimeError('Black or nearly white screenshot')
            except ScriptStop:raise
            except Exception as e:
                reason=str(e)[:300]
                consecutive=0
                self.adbCaptureMode=self.ADB_CAPTURE_MODES[(self.ADB_CAPTURE_MODES.index(self.adbCaptureMode)+1)%len(self.ADB_CAPTURE_MODES)]
                logger.debug(f'Capture stability probe failed: {reason}')
            else:
                consecutive+=1
                if consecutive>=self.ADB_STABLE_FRAMES:return frame
            remaining=deadline-time.monotonic()
            if remaining>0:schedule.sleep(min(self.ADB_STABLE_INTERVAL,remaining))
        raise RuntimeError(f'Capture did not stabilize ({consecutive}/{self.ADB_STABLE_FRAMES} consecutive valid frames): {reason}')
    def _screenshotAdbWithReconnect(self):
        try:return self._screenshotAdb()
        except RuntimeError:
            if not self.captureFailure or not self.name:raise
            now=time.monotonic()
            while self.adbReconnectTimes and now-self.adbReconnectTimes[0]>=self.ADB_RECONNECT_WINDOW:
                self.adbReconnectTimes.popleft()
            if len(self.adbReconnectTimes)>=self.ADB_RECONNECT_LIMIT:
                self.captureFailure+=f' Automatic ADB reconnect limit reached ({self.ADB_RECONNECT_LIMIT} per {self.ADB_RECONNECT_WINDOW} seconds).'
                raise RuntimeError(self.captureFailure)from None
        # Keep the caller's stack and battle objects alive throughout the full
        # restart. Block input until fresh frames have passed stability checks.
        with self.mutex:
            schedule.checkStop()
            self.adbReconnectTimes.append(now)
            logger.warning('Full ADB recovery: restarting server and rebuilding capture, touch and rotation connections; keeping the suspended battle step')
            try:
                self._reconnectAdb(restartServer=True)
                schedule.checkStop()
                frame=self._waitForStableAdbCapture()
                schedule.checkStop()
            except ScriptStop:
                self.captureFailure='Capture recovery cancelled; reconnect device before continuing.'
                raise
            except Exception as e:
                self.captureFailure=f'ADB server restart did not restore stable capture/input: {e}. Capture disabled until device reconnect.'
                raise RuntimeError(self.captureFailure)from e
            self.adbCaptureHealth.clear()
            self.captureFailure=None
            self.captureGeneration+=1
            logger.warning(f'Full ADB recovery complete: {self.ADB_STABLE_FRAMES} consecutive valid frames; continuing the suspended screen read without replaying input')
            return frame
    def screenshot(self):
        with self.captureMutex:
            if self.captureFailure:raise RuntimeError(self.captureFailure)
            while True:
                method=self.screen_proxy.method_name
                if method=='ADBCAP':return self._screenshotAdbWithReconnect()
                try:frame=super().snapshot()
                except Exception as e:
                    if method!='JAVACAP':raise
                    logger.warning(f'JAVACAP capture failed: {e!r}')
                    frame=None
                if method!='JAVACAP' or not self._isInvalidCaptureFrame(frame):
                    self.invalidFrame=0
                    return self._cropScreenshot(frame)
                self.invalidFrame+=1
                if self.invalidFrame<self.JAVACAP_INVALID_LIMIT:
                    time.sleep(.1)
                    continue
                logger.warning('Invalid screenshots from JAVACAP, falling back to ADBCAP')
                self._fallBackToAdbcap()
    def invoke169(self):
        x,y=(lambda r:(int(r.group(1)),int(r.group(2))))(re.search(r'(\d+)x(\d+)',self.adb.raw_shell('wm size')))
        if x*16<y*9:self.adb.raw_shell('wm size %dx%d'%(x,x*16//9))
        elif y*16<x*9:self.adb.raw_shell('wm size %dx%d'%(y*16//9,y))
        self.adjustOffset()
    def revoke169(self):self.adb.raw_shell('wm size reset')
