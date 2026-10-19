"""Offline capture regressions; no emulator or input events are used."""
import importlib.util
import logging
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

import cv2
import numpy
from airtest.core.android.android import Android as Airtest


SOURCE = Path(__file__).resolve().parents[1] / 'FGO-py' / 'fgoAndroid.py'
sys.path.insert(0,str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('capture_under_test', SOURCE)
capture = importlib.util.module_from_spec(spec)
with patch.dict('sys.modules', {
    'fgoConst': SimpleNamespace(KEYMAP={}),
    'fgoLogging': SimpleNamespace(getLogger=logging.getLogger),
}), patch('shutil.which', return_value=None):
    spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.device = capture.Android()
        self.device.render = [0, 0, 1280, 720]
        self.device.border = (0, 0)
        self.device._screen_proxy = SimpleNamespace(method_name='JAVACAP')
        self.switches = []
        self.frames = []
        self.good = numpy.full((720, 1280, 3), 80, dtype=numpy.uint8)
        self.adb = numpy.full((720, 1280, 3), 120, dtype=numpy.uint8)

        def switch(device, method):
            self.switches.append(method)
            device._screen_proxy = SimpleNamespace(method_name=method)

        def snapshot(device):
            if device._screen_proxy.method_name == 'ADBCAP':
                return self.adb
            frame = self.frames.pop(0)
            if isinstance(frame, Exception):
                raise frame
            return frame

        self.enterContext(patch.object(Airtest, 'screen_proxy', property(
            lambda device: device._screen_proxy, switch)))
        self.enterContext(patch.object(Airtest, 'snapshot', snapshot))
        self.enterContext(patch.object(capture.Android, '_useCaptureMethod', switch))
        self.readAdb=self.enterContext(patch.object(capture.Android, '_readAdbScreenshot', side_effect=lambda *args:self.adb))
        self.enterContext(patch.object(capture.time, 'sleep'))
        self.enterContext(patch.object(capture.schedule,'sleep'))
        self.enterContext(patch.object(capture.cv2,'imwrite',return_value=True))
        capture.schedule.reset()
        self.addCleanup(capture.schedule.reset)

    def test_fallback_stays_on_adb_after_old_retry_deadlines(self):
        self.frames = [None] * 3
        with patch.object(capture.time, 'monotonic', return_value=100):
            numpy.testing.assert_array_equal(self.device.screenshot(), self.adb)
        # A recovered JAVACAP must not be probed while this connection is active.
        self.frames = [self.good]
        for elapsed in (61, 121, 301, 601, 3600):
            with patch.object(capture.time, 'monotonic', return_value=100 + elapsed):
                numpy.testing.assert_array_equal(self.device.screenshot(), self.adb)
        self.assertEqual(self.switches, ['ADBCAP'])
        self.assertEqual(len(self.frames), 1)

    def test_transient_bad_frames_recover_without_switching(self):
        self.frames = [None, numpy.zeros_like(self.good), self.good]
        numpy.testing.assert_array_equal(self.device.screenshot(), self.good)
        self.assertEqual(self.switches, [])
        self.assertEqual(self.device.invalidFrame, 0)

    def test_corrupt_white_frames_fall_back_before_returning(self):
        white = numpy.full_like(self.good, 255)
        white[:20, :20] = 0
        self.frames = [white] * 3
        numpy.testing.assert_array_equal(self.device.screenshot(), self.adb)
        self.assertEqual(self.switches, ['ADBCAP'])

    def test_javacap_exceptions_fall_back(self):
        self.frames = [RuntimeError('capture failed')] * 3
        numpy.testing.assert_array_equal(self.device.screenshot(), self.adb)
        self.assertEqual(self.switches, ['ADBCAP'])

    def test_initial_adb_capture_does_not_probe_javacap(self):
        self.device._screen_proxy = SimpleNamespace(method_name='ADBCAP')
        numpy.testing.assert_array_equal(self.device.screenshot(), self.adb)
        self.assertEqual(self.switches, [])

    def test_adb_failure_is_reported(self):
        self.device._screen_proxy = SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=RuntimeError('ADB unavailable')
        with self.assertRaisesRegex(RuntimeError, 'recovery exhausted.*ADB unavailable'):
            self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,self.device.ADB_RECOVERY_ATTEMPTS)
        self.assertEqual(self.switches, [])

    def test_adb_black_frames_are_retried_before_returning(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=[numpy.zeros_like(self.good),None,self.good]
        numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        self.assertEqual(self.readAdb.call_count,3)
        self.assertEqual(self.device.adbCaptureMode,'exec-png')

    def test_adb_can_recover_via_raw_and_keep_that_transport(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=lambda mode,timeout:self.good if mode=='exec-raw' else numpy.zeros_like(self.good)
        numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        self.assertEqual(self.device.adbCaptureMode,'exec-raw')
        self.readAdb.reset_mock()
        numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        self.assertEqual(self.readAdb.call_count,1)
        self.assertEqual(self.readAdb.call_args.args[0],'exec-raw')
        self.assertEqual(self.switches,[])

    def test_persistent_black_capture_never_reaches_detector(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=lambda *args:numpy.zeros_like(self.good)
        with self.assertRaisesRegex(RuntimeError,'recovery exhausted.*Black'):
            self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,self.device.ADB_RECOVERY_ATTEMPTS)
        capture.cv2.imwrite.assert_called_once()

    def test_deadline_bounds_slow_failed_captures(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=RuntimeError('timeout')
        with patch.object(capture.time,'monotonic',side_effect=[0,0,31,31]):
            with self.assertRaisesRegex(RuntimeError,'recovery exhausted'):
                self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,1)
        self.assertEqual(self.readAdb.call_args.args[1],self.device.ADB_CAPTURE_TIMEOUT)

    def test_stop_interrupts_recovery(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        def fail_and_stop(*args):
            capture.schedule.stop('user requested stop')
            return None
        self.readAdb.side_effect=fail_and_stop
        with self.assertRaises(capture.ScriptStop):self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,1)

    def test_crop_is_checked_not_only_emulator_border(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.render=[0,0,1280,740]
        self.device.border=(0,10)
        frame=numpy.zeros((740,1280,3),dtype=numpy.uint8)
        frame[:10]=80
        self.readAdb.side_effect=[frame,self.good]
        numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        self.assertEqual(self.readAdb.call_count,2)

    def test_occasional_success_does_not_reset_persistent_failure_budget(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        black=numpy.zeros_like(self.good)
        self.readAdb.side_effect=([black]*3+[self.good])*15
        for _ in range(14):
            numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        with self.assertRaisesRegex(RuntimeError,'Persistent capture failure: 45/60'):
            self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,60)

    def test_failed_connection_does_not_restart_retry_loop_on_next_call(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=RuntimeError('ADB unavailable')
        with self.assertRaises(RuntimeError):self.device.screenshot()
        calls=self.readAdb.call_count
        capture.schedule.reset()
        for _ in range(3):
            with self.assertRaisesRegex(RuntimeError,'disabled until device reconnect'):
                self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,calls)
        capture.cv2.imwrite.assert_not_called()

    def test_intermittent_transition_frames_do_not_disable_capture(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=([numpy.zeros_like(self.good)]+[self.good]*3)*25
        for _ in range(75):self.device.screenshot()
        self.assertIsNone(self.device.captureFailure)
        self.assertEqual(len(self.device.adbCaptureHealth),60)

    def test_warning_rate_limit_survives_screenshot_call_boundaries(self):
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.readAdb.side_effect=[None]+[self.good]*5*10
        with patch.object(capture.time,'monotonic',return_value=100),patch.object(capture.logger,'warning')as warning:
            for _ in range(10):self.device.screenshot()
            self.assertEqual(warning.call_count,1)

    def test_reconnect_continues_same_caller_without_replaying_input(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=[None]+[self.good]*5
        progress={'turn':7,'skill':2,'phase':'waiting for skill result'}
        def reconnect(**kwargs):
            self.assertEqual(kwargs,{'restartServer':True})
            self.assertFalse(self.device.mutex.acquire(blocking=False))
            self.assertEqual(progress,{'turn':7,'skill':2,'phase':'waiting for skill result'})
        with patch.object(self.device,'_reconnectAdb',side_effect=reconnect)as recovery,patch.object(Airtest,'touch')as touch:
            numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        recovery.assert_called_once()
        touch.assert_not_called()
        self.assertEqual(self.device.captureGeneration,1)
        self.assertIsNone(self.device.captureFailure)
        self.assertEqual(list(self.device.adbCaptureHealth),[])
        self.assertEqual(progress['phase'],'waiting for skill result')

    def test_reconnect_does_not_loop_when_black_frames_persist(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.device.ADB_STABLE_ATTEMPTS=2
        self.readAdb.side_effect=[None,None,None]
        with patch.object(self.device,'_reconnectAdb')as recovery:
            for _ in range(3):
                with self.assertRaisesRegex(RuntimeError,'server restart did not restore stable'):
                    self.device.screenshot()
            self.assertEqual(recovery.call_count,1)
            self.assertEqual(recovery.call_args.kwargs,{'restartServer':True})
        self.assertEqual(self.readAdb.call_count,3)
        self.assertEqual(self.device.captureGeneration,0)

    def test_one_good_frame_does_not_finish_full_recovery(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=[None,self.good,None]+[self.good]*5
        with patch.object(self.device,'_reconnectAdb')as recovery,patch.object(Airtest,'touch')as touch:
            numpy.testing.assert_array_equal(self.device.screenshot(),self.good)
        recovery.assert_called_once_with(restartServer=True)
        self.assertEqual(self.readAdb.call_count,8)
        touch.assert_not_called()
        self.assertEqual(self.device.captureGeneration,1)

    def test_full_connection_error_stops_without_resuming(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=[None]
        with patch.object(self.device,'_reconnectAdb',side_effect=RuntimeError('offline'))as recovery:
            with self.assertRaisesRegex(RuntimeError,'server restart did not restore stable'):
                self.device.screenshot()
        recovery.assert_called_once_with(restartServer=True)
        self.assertEqual(self.device.captureGeneration,0)

    def test_intermittent_frames_never_pass_stability_check(self):
        self.device.ADB_STABLE_ATTEMPTS=12
        self.device.captureFailure='recovering'
        self.readAdb.side_effect=[self.good,None]*6
        with self.assertRaisesRegex(RuntimeError,'did not stabilize'):
            self.device._waitForStableAdbCapture()
        self.assertEqual(self.readAdb.call_count,12)
        self.assertEqual(self.device.captureFailure,'recovering')

    def test_stop_during_stability_check_keeps_input_disabled(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=[None,self.good]
        with patch.object(self.device,'_reconnectAdb'),patch.object(capture.schedule,'sleep',side_effect=lambda *_:capture.schedule.stop('stop')):
            with self.assertRaises(capture.ScriptStop):self.device.screenshot()
        self.assertEqual(self.device.captureGeneration,0)
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.device.press('A')

    def test_reconnect_rate_limit_survives_brief_successes(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=([None]+[self.good]*5)*2+[None]
        with patch.object(capture.time,'monotonic',return_value=100),patch.object(self.device,'_reconnectAdb')as recovery:
            for _ in range(2):self.device.screenshot()
            with self.assertRaisesRegex(RuntimeError,'reconnect limit reached'):
                self.device.screenshot()
            self.assertEqual(recovery.call_count,2)

    def test_old_reconnect_attempts_expire_from_budget(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.device.adbReconnectTimes.extend([1,2])
        self.readAdb.side_effect=[None]+[self.good]*5
        with patch.object(capture.time,'monotonic',return_value=700),patch.object(self.device,'_reconnectAdb')as recovery:
            self.device.screenshot()
            recovery.assert_called_once()
        self.assertEqual(list(self.device.adbReconnectTimes),[700])

    def test_stop_during_reconnect_never_resumes_actions(self):
        self.device.name='127.0.0.1:62001'
        self.device._screen_proxy=SimpleNamespace(method_name='ADBCAP')
        self.device.ADB_RECOVERY_ATTEMPTS=1
        self.readAdb.side_effect=[None]+[self.good]*5
        with patch.object(self.device,'_reconnectAdb',side_effect=lambda **_:capture.schedule.stop('user stopped')):
            with self.assertRaises(capture.ScriptStop):self.device.screenshot()
        self.assertEqual(self.readAdb.call_count,1)
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.device.press('A')

    def test_input_is_blocked_after_unrecoverable_capture(self):
        self.device.captureFailure='capture unavailable'
        with patch.object(Airtest,'touch')as touch:
            with self.assertRaisesRegex(RuntimeError,'capture unavailable'):self.device.press('A')
            with self.assertRaisesRegex(RuntimeError,'capture unavailable'):self.device.touch((1,1))
        touch.assert_not_called()


class AdbTransportTests(unittest.TestCase):
    def setUp(self):
        self.device=capture.Android()
        self.device.adb=SimpleNamespace(display_id=None,sdk_version=32,cmd=Mock(),line_breaker=b'\r\n')
        # Include distinct channels to catch RGB/BGR mistakes and binary bytes
        # that newline replacement would corrupt in exec-out PNGs.
        self.frame=numpy.random.default_rng(1).integers(0,256,(40,60,3),dtype=numpy.uint8)

    def test_exec_png_uses_timeout_and_preserves_binary_data(self):
        self.device.adb.cmd.return_value=cv2.imencode('.png',self.frame)[1].tobytes()
        numpy.testing.assert_array_equal(self.device._readAdbScreenshot('exec-png',2),self.frame)
        self.device.adb.cmd.assert_called_once_with(['exec-out','screencap','-p'],ensure_unicode=False,timeout=2)

    def test_shell_png_supports_legacy_line_endings(self):
        self.device.adb.cmd.return_value=cv2.imencode('.png',self.frame)[1].tobytes().replace(b'\n',b'\r\n')
        numpy.testing.assert_array_equal(self.device._readAdbScreenshot('shell-png',5),self.frame)

    def test_raw_formats_and_header_versions_match_png_colors(self):
        for fmt in (1,2,3,5):
            for header_size in (12,16):
                with self.subTest(fmt=fmt,header_size=header_size):
                    pixels=cv2.cvtColor(self.frame,cv2.COLOR_BGR2RGB if fmt==3 else cv2.COLOR_BGR2BGRA if fmt==5 else cv2.COLOR_BGR2RGBA)
                    raw=struct.pack('<III',60,40,fmt)+(b'\0'*4 if header_size==16 else b'')+pixels.tobytes()
                    numpy.testing.assert_array_equal(self.device._decodeRawScreenshot(raw,header_size),self.frame)

    def test_truncated_modern_raw_cannot_be_mistaken_for_legacy_header(self):
        pixels=cv2.cvtColor(self.frame,cv2.COLOR_BGR2RGBA)
        raw=struct.pack('<IIII',60,40,1,1)+pixels.tobytes()
        with self.assertRaisesRegex(RuntimeError,'Truncated'):
            self.device._decodeRawScreenshot(raw[:-4])

    def test_raw_transport_preserves_colors_and_uses_timeout(self):
        pixels=cv2.cvtColor(self.frame,cv2.COLOR_BGR2RGBA)
        self.device.adb.cmd.return_value=struct.pack('<IIII',60,40,1,1)+pixels.tobytes()
        numpy.testing.assert_array_equal(self.device._readAdbScreenshot('exec-raw',3),self.frame)
        self.device.adb.cmd.assert_called_once_with(['exec-out','screencap'],ensure_unicode=False,timeout=3)

    def test_old_android_orientation_matches_airtest_adbcap(self):
        self.device.adb.sdk_version=24
        self.device.adb.display_info={'orientation':1}
        self.device.adb.cmd.return_value=cv2.imencode('.png',self.frame)[1].tobytes()
        numpy.testing.assert_array_equal(self.device._readAdbScreenshot('exec-png',5),capture.aircv.rotate(self.frame,90,clockwise=False))

    def test_raw_truncated_or_unknown_layout_is_rejected(self):
        for raw in (b'',struct.pack('<III',60,40,1)+b'\0'*10,struct.pack('<III',60,40,99),struct.pack('<III',0,0,1)):
            with self.subTest(raw=raw):
                with self.assertRaises(RuntimeError):self.device._decodeRawScreenshot(raw)

    def test_display_zero_is_preserved(self):
        self.device.adb.display_id=0
        self.device.adb.cmd.return_value=cv2.imencode('.png',self.frame)[1].tobytes()
        self.device._readAdbScreenshot('exec-png',5)
        self.assertEqual(self.device.adb.cmd.call_args.args[0],['exec-out','screencap','-d','0','-p'])

    def test_fallback_installs_adb_without_unbounded_auto_probe(self):
        old=Mock()
        self.device._screen_proxy=old
        with patch.object(capture.ScreenProxy,'auto_setup',side_effect=AssertionError('unexpected probe')):
            self.device._fallBackToAdbcap()
        old.teardown_stream.assert_called_once()
        self.assertEqual(self.device.screen_proxy.method_name,'ADBCAP')
        self.device.adb.cmd.assert_not_called()

    def configure_reconnect(self):
        self.device.adb.serialno='127.0.0.1:62001'
        self.device.adb.cmd.side_effect=lambda args,**kwargs:'device' if args==['get-state']else''
        self.device.ori_method='MINICAP'
        oldWatcher=Mock()
        oldWatcher._t=None
        self.device.rotation_watcher=oldWatcher
        oldTouch=Mock()
        self.device._touch_proxy=oldTouch
        self.device._screen_proxy=Mock()
        newTouch=Mock(method_name='MAXTOUCH')
        newWatcher=self.enterContext(patch.object(capture,'RotationWatcher')).return_value
        self.enterContext(patch.object(Airtest,'touch_proxy',property(lambda _:newTouch)))
        self.enterContext(patch.object(self.device,'adjustOffset'))
        return oldWatcher,oldTouch,newWatcher,newTouch

    def test_reconnect_targets_only_selected_endpoint_and_rebuilds_helpers(self):
        oldWatcher,oldTouch,newWatcher,newTouch=self.configure_reconnect()
        cmd=self.device.adb.cmd
        self.device._reconnectAdb()
        self.assertIs(self.device.adb.cmd,cmd)
        self.assertEqual([c.args[0]for c in cmd.call_args_list],[['disconnect','127.0.0.1:62001'],['connect','127.0.0.1:62001'],['wait-for-device'],['get-state']])
        for c in cmd.call_args_list:self.assertEqual(c.kwargs['timeout'],5)
        self.assertFalse(cmd.call_args_list[0].kwargs['device'])
        self.assertFalse(cmd.call_args_list[1].kwargs['device'])
        oldWatcher.teardown.assert_called_once()
        oldTouch.teardown.assert_called_once()
        self.assertIs(self.device.rotation_watcher,newWatcher)
        self.assertEqual(newWatcher.reg_callback.call_count,2)
        self.device.adjustOffset.assert_called_once()
        newTouch.touch.assert_not_called()
        self.assertEqual(self.device.screen_proxy.method_name,'ADBCAP')

    def test_usb_reconnect_does_not_issue_global_disconnect(self):
        self.configure_reconnect()
        self.device.adb.serialno='usb-device-123'
        self.device._reconnectAdb()
        self.assertEqual(self.device.adb.cmd.call_args_list[0].args[0],['reconnect'])
        self.assertNotIn('device',self.device.adb.cmd.call_args_list[0].kwargs)

    def test_server_restart_reconnects_endpoint_and_rebuilds_input(self):
        oldWatcher,oldTouch,newWatcher,newTouch=self.configure_reconnect()
        oldScreen=self.device._screen_proxy
        self.device._reconnectAdb(restartServer=True)
        oldScreen.teardown_stream.assert_called_once()
        calls=self.device.adb.cmd.call_args_list
        self.assertEqual([c.args[0]for c in calls],[['kill-server'],['start-server'],['connect','127.0.0.1:62001'],['wait-for-device'],['get-state']])
        for c in calls[:2]:self.assertEqual(c.kwargs,{'timeout':10,'device':False})
        oldWatcher.teardown.assert_called_once()
        oldTouch.teardown.assert_called_once()
        self.assertIs(self.device.rotation_watcher,newWatcher)
        newTouch.touch.assert_not_called()
        self.assertEqual(self.device.screen_proxy.method_name,'ADBCAP')

    def test_stop_during_server_shutdown_still_starts_service_but_not_input(self):
        self.configure_reconnect()
        def command(args,**kwargs):
            if args==['kill-server']:capture.schedule.stop('user stopped')
            return''
        self.device.adb.cmd.side_effect=command
        try:
            with self.assertRaises(capture.ScriptStop):self.device._reconnectAdb(restartServer=True)
            self.assertEqual([c.args[0]for c in self.device.adb.cmd.call_args_list],[['kill-server'],['start-server']])
            self.device.adjustOffset.assert_not_called()
        finally:capture.schedule.reset()

    def test_transport_failure_restores_command_method(self):
        self.configure_reconnect()
        original=self.device.adb.cmd
        original.side_effect=RuntimeError('offline')
        with self.assertRaisesRegex(RuntimeError,'offline'):self.device._reconnectAdb()
        self.assertIs(self.device.adb.cmd,original)


if __name__ == '__main__':
    unittest.main()
