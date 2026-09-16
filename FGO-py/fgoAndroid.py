import os,re,shutil,threading,time,cv2,numpy
from airtest.core.android.adb import ADB
from airtest.core.android.android import Android as Airtest
from airtest.core.android.constant import CAP_METHOD
from fgoConst import KEYMAP
from fgoLogging import getLogger
logger=getLogger('Android')

if adb:=shutil.which('adb'):
    logger.warning(f'Using Adb in PATH: {adb}')
    ADB.builtin_adb_path=staticmethod(lambda:adb)

class Android(Airtest):
    JAVACAP_INVALID_LIMIT=3
    def __init__(self,serial=None,**kwargs):
        self.mutex=threading.Lock()
        self.captureMutex=threading.Lock()
        self.invalidFrame=0
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
        if not self.name:return False
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
        with self.mutex:super().touch([round(pos[i]/self.scale+self.border[i]+self.render[i])for i in range(2)])
    def swipe(self,begin,end):
        p1,p2=[numpy.array(self._touch_point_by_orientation([i[j]/self.scale+self.border[j]+self.render[j]for j in range(2)]))for i in(begin,end)]
        vd=p2-p1
        lvd=numpy.linalg.norm(vd)
        vd/=.2*self.scale*lvd
        vx=numpy.array([0.,0.])
        def send(method,pos):self.touch_proxy.handle(' '.join((method,'0',*[str(i)for i in self.touch_proxy.transform_xy(*pos)],'50\nc\n')))
        with self.mutex:
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
        with self.mutex:super().touch(self.key[key])
    def pinch(self):
        with self.mutex:super().pinch(percent=.2)
    @staticmethod
    def _isInvalidJavacapFrame(frame):
        if frame is None or not frame.size or not numpy.any(frame):return True
        # A broken JAVACAP JPEG can decode successfully as an almost entirely
        # white image with a solid black rectangle, so it must not reach the
        # image detector merely because it contains a few non-zero pixels.
        return numpy.mean(numpy.all(frame>250,axis=2))>.9
    def _useCaptureMethod(self,method):
        self.screen_proxy=method
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
    def screenshot(self):
        with self.captureMutex:
            while True:
                method=self.screen_proxy.method_name
                try:frame=super().snapshot()
                except Exception as e:
                    if method!='JAVACAP':raise
                    logger.warning(f'JAVACAP capture failed: {e!r}')
                    frame=None
                if method!='JAVACAP' or not self._isInvalidJavacapFrame(frame):
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
