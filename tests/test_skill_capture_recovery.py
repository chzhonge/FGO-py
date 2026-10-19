"""Exercise production skill methods without launching the GUI/OCR threads."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace,MethodType
import unittest
from unittest.mock import Mock,patch

import numpy
from test_android_capture import capture


SOURCE=Path(__file__).resolve().parents[1]/'FGO-py'/'fgoKernel.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf-8'))


def load_skill(name,frames):
    owner=next(n for n in TREE.body if isinstance(n,ast.ClassDef)and n.name==name)
    method=next(n for n in owner.body if isinstance(n,ast.FunctionDef)and n.name=='castServantSkill')
    target_key=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)and n.name=='getSkillTargetKey')
    device=SimpleNamespace(press=Mock(),perform=Mock(),touch=Mock())
    namespace={'Detect':Mock(side_effect=frames),'fgoDevice':SimpleNamespace(device=device),
               'logger':logging.getLogger('skill-test'),'time':SimpleNamespace(time=Mock(return_value=0)),
               'ScriptStop':capture.ScriptStop,'waitTurnBegin':Mock()}
    exec(compile(ast.Module(body=[target_key,method],type_ignores=[]),str(SOURCE),'exec'),namespace)
    turn=SimpleNamespace(countDown=[[[0]*3 for _ in range(3)],[0]*3],getSkillInfo=Mock(return_value=2),
                         servant=[[0,0,0,0,0,0,[(0,2)]*3]for _ in range(3)])
    bound=MethodType(namespace['castServantSkill'],turn)
    return lambda:bound(0,0,2)if name=='Turn'else bound(0,0),device,namespace


def screen(ready=False,targets=0):
    return SimpleNamespace(getSkillNoneClose=lambda:None,isSkillCastFailed=lambda:False,
                           getSkillTargetCount=lambda:targets,isTurnBegin=lambda:True,
                           isSkillReady=lambda *_:ready)


class SkillRecoveryTests(unittest.TestCase):
    def test_missed_animation_with_cooldown_does_not_repeat_skill(self):
        for name in ('ClassicTurn','Turn'):
            with self.subTest(name=name):
                cast,device,_=load_skill(name,[screen(ready=False)])
                cast()
                device.press.assert_called_once_with('A')

    def test_actual_missed_tap_can_retry_when_skill_is_still_ready(self):
        for name in ('ClassicTurn','Turn'):
            with self.subTest(name=name):
                cast,device,namespace=load_skill(name,[screen(ready=True),screen(ready=False)])
                namespace['time'].time.side_effect=[0,40,40]
                cast()
                self.assertEqual([c.args for c in device.press.call_args_list],[('A',),('A',)])

    def test_visible_target_dialog_is_completed_without_replaying_skill(self):
        for name in ('ClassicTurn','Turn'):
            with self.subTest(name=name):
                cast,device,_=load_skill(name,[screen(targets=3)])
                cast()
                if name=='ClassicTurn':
                    self.assertEqual([c.args for c in device.press.call_args_list],[('A',),('3',)])
                else:
                    device.press.assert_called_once_with('A')
                    device.perform.assert_called_once_with('3\x08',(300,700))

    def test_capture_reconnect_resumes_actual_skill_wait_without_second_tap(self):
        for name,failures in ((name,n)for name in('ClassicTurn','Turn')for n in(1,2)):
            with self.subTest(name=name,recovery_stages=failures):
                android=capture.Android()
                android.name='127.0.0.1:62001'
                android.render=[0,0,1280,720]
                android.border=(0,0)
                android._screen_proxy=SimpleNamespace(method_name='ADBCAP')
                android.ADB_RECOVERY_ATTEMPTS=1
                frame=numpy.full((720,1280,3),80,dtype=numpy.uint8)
                def detect(*_):
                    numpy.testing.assert_array_equal(android.screenshot(),frame)
                    return screen(ready=False)
                cast,device,_=load_skill(name,detect)
                with patch.object(android,'_readAdbScreenshot',side_effect=[None]*failures+[frame]*5),patch.object(android,'_reconnectAdb')as reconnect,patch.object(capture.schedule,'sleep'):
                    cast()
                reconnect.assert_called_once_with(restartServer=True)
                device.press.assert_called_once_with('A')
                self.assertEqual(android.captureGeneration,1)
                self.assertIsNone(android.captureFailure)


if __name__=='__main__':unittest.main()
