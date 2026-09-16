"""Offline capture regressions; no emulator or input events are used."""
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy
from airtest.core.android.android import Android as Airtest


SOURCE = Path(__file__).resolve().parents[1] / 'FGO-py' / 'fgoAndroid.py'
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
        self.enterContext(patch.object(capture.time, 'sleep'))

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
        with patch.object(Airtest, 'snapshot', side_effect=RuntimeError('ADB unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'ADB unavailable'):
                self.device.screenshot()
        self.assertEqual(self.switches, [])


if __name__ == '__main__':
    unittest.main()
