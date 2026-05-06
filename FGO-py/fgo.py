import argparse,os,sys
from fgoConst import VERSION

os.chdir(os.path.dirname(os.path.abspath(__file__)))
try:
    with open("../.git/HEAD")as f:head=f.read().strip()
except FileNotFoundError:
    head='master'

new_argv=[sys.argv[0]]
for i in sys.argv[1:]:
    if i.lower()not in['gui','cli','web']and not i.startswith('-')and('-d'not in sys.argv and'--device'not in sys.argv):
        if'.'in i or':'in i or i.lower()=='auto':
            new_argv.append('-d')
    new_argv.append(i)
sys.argv[:]=new_argv

parser=argparse.ArgumentParser(description=f'FGO-py {VERSION}')
parser.add_argument('entrypoint',help='Program entry point (default: %(default)s)',type=str.lower,choices=['gui','cli','web'],default='gui'if head.endswith('master')else'cli',nargs='?')
parser.add_argument('-v','--version',help='Show FGO-py version',action='version',version=VERSION)
parser.add_argument('-l','--loglevel',help='Change the console log level (default: %(default)s)',type=str.upper,choices=['DEBUG','INFO','WARNING','CRITICAL','ERROR'],default='INFO')
parser.add_argument('-c','--config',help='Config file path (default: %(default)s)',type=str,default='fgoConfig.json')
parser.add_argument('-r','--readonly',help='Do not save configuration file on exit',action='store_false')
parser.add_argument('--no-color',help='Disable colored console output',action='store_true')
parser.add_argument('-d','--device',help='Device name or address to connect',type=str)
arg=parser.parse_args()

if arg.no_color:os.environ['NO_COLOR']='1'

match arg.entrypoint:
    case'gui':from fgoGui import main
    case'cli':from fgoCli import main
    case'web':from fgoWebServer import main

import fgoLogging
fgoLogging.logger.handlers[-1].setLevel(arg.loglevel)

from fgoConfig import Config
config=Config(arg.config)
if not config.runOnce:config.runOnce=VERSION
elif config.runOnce!=VERSION:
    from fgoRunOnce import runOnce
    if runOnce(config):
        config.runOnce=VERSION
        config.save()
        sys.exit()
    config.runOnce=VERSION

if not config.farming:
    from fgoKernel import farming
    farming.stop=True

try:main(config, arg.device)
except Exception as e:fgoLogging.logger.exception(e)
finally:
    if arg.readonly:config.save()
