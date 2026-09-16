# Stars  Cosmos Gods  Animus    Antrum       Unbirth    Anima Animusphere
# 星の形.宙の形.神の形.我の形.天体は空洞なり.空洞は虚空なり.虚空には神ありき.
# 地を照らし,空に在り,天上の座標を示せ.
# カルディアの灯よ.
# どうか今一度,旅人の標とならん事を.
# ここで,Bgo運営の敗北を宣言する!
# .        OO---O---O-o\
# .       // \ / \ / \ \\
# .      OO   O   O   O \\
# .     // \   \ /   / \ \\
# .    oO---O---O---O---O-Oo
# .     \\ /   / \   \ / //
# .      \O   O   O   O //
# .       \\ / \ / \ / //
# .        oO---O---Oo-O
# .             ^^
# .  Grand Order/Anima Animusphere
# .     冠位指定/人理保障天球
'Full-automatic FGO Script'
from fgoConst import VERSION
__version__=VERSION
__author__='hgjazhgj'
import logging,numpy,pulp,random,re,time,threading,gc
import fgoDevice
from itertools import permutations
from functools import wraps
from fgoDetect import Detect,XDetect
from fgoFuse import fuse
from fgoImageListener import ImageListener
from fgoLogging import getLogger,logit
from fgoMetadata import servantData,missionMat,missionTag,missionQuest
from fgoReishift import reishift
from fgoSchedule import ScriptStop,schedule
logger=getLogger('Kernel')

friendImg=ImageListener('fgoImage/friend/')
mailImg=ImageListener('fgoImage/mail/')
import os
def setFriendDir(dir_name):
    global friendImg
    path = f'fgoImage/friend/{dir_name}/' if dir_name else 'fgoImage/friend/'
    if not hasattr(friendImg, 'path') or os.path.abspath(path) + os.sep != friendImg.path:
        logger.info(f'Set friend image dir to {path}')
        friendImg = ImageListener(path)

mutex=threading.Lock()
def serialize(lock):
    def decorator(func):
        @wraps(func)
        def wrapper(*args,**kwargs):
            with lock:return func(*args,**kwargs)
        return wrapper
    return decorator
def waitTurnBegin(stabilize=1):
    dialogRetry=0
    while True:
        detect=Detect()
        if close:=detect.getSkillNoneClose():
            dialogRetry+=1
            if dialogRetry>5:raise ScriptStop('Skill Dialog Stuck')
            logger.warning(f'Close skill dialog at {close}')
            fgoDevice.device.touch(close)
            schedule.sleep(.5)
            continue
        if detect.isTurnBegin():
            time.sleep(stabilize)
            stable=Detect(0)
            if close:=stable.getSkillNoneClose():
                logger.warning(f'Close skill dialog at {close}')
                fgoDevice.device.touch(close)
                schedule.sleep(.5)
                continue
            if stable.isTurnBegin():return
def getStableTurnDetect(interval=.3,attempts=6):
    previous=None
    detect=None
    for _ in range(attempts):
        detect=Detect(interval)
        if not detect.isTurnBegin():
            previous=None
            continue
        ready=tuple(detect.isSkillReady(i,j)for i in range(3)for j in range(3))
        if ready==previous:return detect
        previous=ready
    raise ScriptStop('Battle Controls Unstable')
def getSkillTargetKey(target,count):
    # Explicit targets are fixed field positions (1=left, 2=middle, 3=right).
    # A dialog with only one available choice places that choice in the middle.
    if count==1:return'3'
    if target in(1,2,3):return str(target+1)
    return('3','2','3')[count-1]
def waitCardSelection(interval=.25,attempts=8):
    recovery=0
    while True:
        detect=None
        for _ in range(attempts):
            detect=Detect(interval)
            try:color=detect.getCardColorOnce()
            except (TypeError,ValueError,IndexError,AssertionError):continue
            fuse.reset(detect)
            if recovery:logger.warning(f'Card selection recovered after {recovery} recovery cycle(s)')
            return detect,color
        recovery+=1
        if detect is not None:detect.save('fgoLog/CardSelect_Current',appendTime=False)
        if detect is not None and detect.isTurnBegin():
            logger.warning(f'Card selection did not open; pressing Attack again (recovery {recovery})')
            fgoDevice.device.perform(' ',(2100,))
        else:
            logger.warning(f'Card selection unavailable; waiting for screen transition (recovery {recovery})')
            schedule.sleep(1)
def guardian():
    logger=logging.getLogger('Guardian')
    prev=None
    while True:
        gc.collect()
        while XDetect.cache is prev:time.sleep(3)
        if XDetect.cache.isNetworkError():
            logger.warning('Reconnecting')
            fgoDevice.device.press('K')
        prev=XDetect.cache
threading.Thread(target=guardian,daemon=True,name='Guardian').start()
class Farming:
    def __init__(self):
        self.logger=getLogger('Farming')
        self.stop=False
    def __call__(self):
        time.sleep(100)
        while not self.stop:
            if not fgoDevice.device.available:continue
            time.sleep(self.run()+30)
            XDetect.clear()
            fuse.clear()
            gc.collect()
    @serialize(mutex)
    def run(self):
        from fgoFarming import farming
        try:
            return farming()
        except Exception as e:
            logger.exception(e)
            return 0
farming=Farming()
threading.Thread(target=farming,daemon=True,name='Farming').start()
def setup():
    raise NotImplementedError
    if not fgoDevice.device.isInGame():
        fgoDevice.device.launch()
        while not Detect(1).isGameLaunch():pass
        while not Detect(1).isGameAnnounce():fgoDevice.device.press('\xBB')
        fgoDevice.device.press('\x08')
    elif False:...
@serialize(mutex)
def fpSummon():
    while fuse.value<30:
        if Detect().isSummonContinue():fgoDevice.device.perform('MK',(600,2700))
        fgoDevice.device.press('\x08')
@serialize(mutex)
def lottery():
    Detect().setupLottery()
    count=0
    while(count:=0 if Detect().isLotteryContinue()else count+1)<5:
        for _ in range(random.randint(10,100)):fgoDevice.device.press('2')
# @serialize(mutex)
# def mining():
#     while fuse.value<30:
#         if Detect().isMining():fgoDevice.device.perform('K',(300,))
#         fgoDevice.device.perform('9Z',(300,300))
@serialize(mutex)
def mail():
    assert mailImg.flush()
    Detect().setupMailDone()
    while True:
        while any((pos:=Detect.cache.findMail(i[1]))and(fgoDevice.device.touch(pos),True)[-1]for i in mailImg.items()):
            while not Detect().isMailDone():pass
        fgoDevice.device.swipe((400,600),(400,200))
        if Detect().isMailListEnd():break
@serialize(mutex)
def synthesis():
    while True:
        fgoDevice.device.perform('8',(1000,))
        for i,j in((i,j)for i in range(4)for j in range(7)):fgoDevice.device.touch((133+133*j,253+142*i),100)
        if Detect().isSynthesisFinished():break
        fgoDevice.device.perform('  KK\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB\xBB',(800,300,300,1000,150,150,150,150,150,150,150,150,150,150,150,150,150,150,150))
        while not Detect().isSynthesisBegin():fgoDevice.device.press('\xBB')
@serialize(mutex)
def dailyFpSummon():
    while not Detect(0,1).isMainInterface():pass
    fgoDevice.device.perform(' Z',(1000,2000))
    while not Detect(.5).isMainInterface():pass
    while not Detect(1.5).isSummonFp():fgoDevice.device.press('\xBC')
    fgoDevice.device.perform('\xBDJ',(800,3000))
    while not Detect(.5).isSummonContinue():fgoDevice.device.press(' ')
    fgoDevice.device.perform('\x67\x67',(1200,2000))
@serialize(mutex)
def dailyStorySummon():
    while not Detect(0,1).isMainInterface():pass
    fgoDevice.device.press(' ')
    if not Detect(1).isSummonStory():
        fgoDevice.device.perform(' \x67',(1000,2000))
        return
    fgoDevice.device.press('\xBD')
    while not Detect(2.5).isMainInterface():pass
    fgoDevice.device.perform('GJ',(800,3000))
    while not Detect(.5).isSummonFinish():fgoDevice.device.press(' ')
    fgoDevice.device.perform('\x67\x67',(1200,2000))
@serialize(mutex)
def summonHistory():
    Detect().setupSummonHistory()
    while not Detect.cache.isSummonHistoryListEnd():
        fgoDevice.device.swipe((930,500),(930,200))
        Detect(.4).getSummonHistory()
    return{'type':'SummonHistory'}|dict(zip(('value','file'),Detect.cache.saveSummonHistory()))
@serialize(mutex)
def bench(times=20,touch=True,screenshot=True):
    if not(touch or screenshot):touch=screenshot=True
    screenshotBench=[]
    for _ in range(times*screenshot):
        begin=time.time()
        fgoDevice.device.screenshot()
        screenshotBench.append(time.time()-begin)
    touchBench=[]
    for _ in range(times*touch):
        begin=time.time()
        fgoDevice.device.press('\xBB')
        touchBench.append(time.time()-begin)
    return{
        'type':'Bench',
        'touch':(sum(touchBench)-max(touchBench)-min(touchBench))*1000/(times-2)if touch else None,
        'screenshot':(sum(screenshotBench)-max(screenshotBench)-min(screenshotBench))*1000/(times-2)if screenshot else None,
    }
@serialize(mutex)
def goto(quest):
    while not Detect(0,1).isMainInterface():pass
    fgoDevice.device.press(' ')
    fgoDevice.device.perform(*((' ',(600,))if Detect(.6).isTerminal()else('S',(1500,))))
    reishift(quest)
    schedule.sleep(.5)
    for _ in range(4):
        if Detect(.4).isQuestListBegin():break
        fgoDevice.device.swipe((1000,200),(1000,600))
    while not Detect(.4).isQuestFreeContains(quest[0]):fgoDevice.device.swipe((1000,600),(1000,200))
    while not Detect(.4).isQuestFreeFirst(quest[0]):fgoDevice.device.swipe((1000,395),(1000,300))
@serialize(mutex)
def weeklyMission():
    while not Detect(0,1).isMainInterface():pass
    fgoDevice.device.perform('B',(800,))
    while not Detect(.4).isWeeklyMission():pass
    fgoDevice.device.perform('2N',(100,1000))
    Detect().setupWeeklyMission()
    while not Detect.cache.isWeeklyMissionListEnd():
        fgoDevice.device.swipe((1000,600),(1000,300))
        Detect(.4).getWeeklyMission()
    x=[pulp.LpVariable('_'.join(str(j)for j in i),lowBound=0,cat=pulp.LpInteger)for i in missionQuest]
    prob=pulp.LpProblem('WeeklyMission',sense=pulp.LpMinimize)
    prob+=pulp.lpDot(missionMat[0],x)
    for count in(count for target,minion,count in Detect.cache.saveWeeklyMission()if(logger.info(f'Add [{"|".join(target)}],{minion},{count}')or True if(coefficient:=sum((j for i in target for j,k in zip(missionMat,missionTag)if i in k and(minion or'从者'in k)),numpy.zeros(missionMat.shape[1]))).any()else logger.error(f'Invalid Target [{"|".join(target)}],{minion},{count}'))):prob+=pulp.lpDot(coefficient,x)>=count
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    logger.info(f'AP: {prob.objective.value():.0f}')
    fgoDevice.device.press('\x67')
    return[(tuple(int(i)for i in v.name.split('_')),int(v.varValue))for v in prob.variables()if v.varValue]
class ClassicTurn:
    skillInfo=[[[0,0,0,7],[0,0,0,7],[0,0,0,7]],[[0,0,0,7],[0,0,0,7],[0,0,0,7]],[[0,0,0,7],[0,0,0,7],[0,0,0,7]],[[0,0,0,7],[0,0,0,7],[0,0,0,7]],[[0,0,0,7],[0,0,0,7],[0,0,0,7]],[[0,0,0,7],[0,0,0,7],[0,0,0,7]]]
    houguInfo=[[1,7],[1,7],[1,7],[1,7],[1,7],[1,7]]
    masterSkill=[[0,0,0,7],[0,0,0,7],[0,0,0,0,7]]
    def __init__(self):
        ClassicTurn.friendInfo=[[[-1,-1,-1,-1],[-1,-1,-1,-1],[-1,-1,-1,-1]],[-1,-1]]
        self.stage=0
        self.stageTurn=0
        self.servant=[0,1,2]
        self.orderChange=[0,1,2,3,4,5]
        self.countDown=[[[0,0,0],[0,0,0],[0,0,0]],[0,0,0]]
    def __call__(self,turn):
        waitTurnBegin()
        previousStage=self.stage
        self.stage,self.stageTurn=[t:=Detect(.2).getStage(),1+self.stageTurn*(self.stage==t)]
        stable=getStableTurnDetect()
        self.friend=[stable.isServantFriend(i)for i in range(3)]
        if turn==1:
            stable.setupServantDead(self.friend)
            self.stageTotal=stable.getStageTotal()
            self.servant=[6 if self.servant[i]>=6 or stable.getFieldServantClassRank(i)is None else self.servant[i]for i in range(3)]
        else:
            changed=[self.servant[i]<6 and stable.isServantDead(i,self.friend[i])for i in range(3)]
            if self.stage!=previousStage and all(changed):
                logger.warning('Ignored simultaneous servant changes during stage transition')
                stable.setupServantDead(self.friend)
                changed=[False]*3
            for i in(i for i in range(3)if changed[i]):
                self.servant[i]=max(self.servant)+1
                self.countDown[0][i]=[0,0,0]
        logger.info(f'Turn {turn} Stage {self.stage} StageTurn {self.stageTurn} {self.servant}')
        if self.stageTurn==1:Detect.cache.setupEnemyGird()
        self.dispatchSkill()
        fgoDevice.device.perform(' ',(2100,))
        detect,color=waitCardSelection()
        fgoDevice.device.perform(self.selectCard(detect,color),(300,300,2300,1300,6000))
    def dispatchSkill(self):
        self.countDown=[[[max(0,j-1)for j in i]for i in self.countDown[0]],[max(0,i-1)for i in self.countDown[1]]]
        while(s:=[(self.getSkillInfo(i,j,3),0,(i,j))for i in range(3)if self.servant[i]<6 for j in range(3)if self.countDown[0][i][j]==0 and(t:=self.getSkillInfo(i,j,0))and(min(t,self.stageTotal)<self.stage or(min(t,self.stageTotal)==self.stage and self.getSkillInfo(i,j,1)<=self.stageTurn))and Detect.cache.isSkillReady(i,j)]+[(self.masterSkill[i][-1],1,(i,))for i in range(3)if self.countDown[1][i]==0 and self.masterSkill[i][0]and(min(self.masterSkill[i][0],self.stageTotal)<self.stage or(min(self.masterSkill[i][0],self.stageTotal)==self.stage and self.masterSkill[i][1]<=self.stageTurn))]):
            _,cast,arg=min(s,key=lambda x:x[0])
            [self.castServantSkill,self.castMasterSkill][cast](*arg)
            waitTurnBegin()
    @logit(logger,logging.INFO)
    def selectCard(self,detect,cardColor):return''.join((lambda hougu,sealed,color,resist,critical:(fgoDevice.device.perform('\x67\x68\x69\x64\x65\x66'[numpy.argmax([detect.getEnemyHp(i)for i in range(6)])],(500,))if any(hougu)or self.stageTurn==1 else 0,['678'[i]for i in sorted((i for i in range(3)if hougu[i]),key=lambda x:self.getHouguInfo(x,1))]+['12345'[i]for i in sorted(range(5),key=(lambda x:-color[x]*resist[x]*(not sealed[x])*(1+critical[x])))]if any(hougu)else(lambda group:['12345'[i]for i in(lambda choice:choice+tuple({0,1,2,3,4}-set(choice)))(logger.debug('cardRank'+','.join(('  'if i%5 else'\n')+f'({j}, {k:5.2f})'for i,(j,k)in enumerate(sorted([(card,(lambda colorChain,firstCardBonus:sum((firstCardBonus+[1.,1.2,1.4][i]*color[j])*(1+critical[j])*resist[j]*(not sealed[j])for i,j in enumerate(card))+(not any(sealed[i]for i in card))*(4.8*colorChain+(firstCardBonus+1.)*(3 if colorChain else 1.8)*(len({group[i]for i in card})==1)*resist[card[0]]))(len({color[i]for i in card})==1,.3*(color[card[0]]==1.1)))for card in permutations(range(5),3)],key=lambda x:-x[1]))))or max(permutations(range(5),3),key=lambda card:(lambda colorChain,firstCardBonus:sum((firstCardBonus+[1.,1.2,1.4][i]*color[j])*(1+critical[j])*resist[j]*(not sealed[j])for i,j in enumerate(card))+(not any(sealed[i]for i in card))*(4.8*colorChain+(firstCardBonus+1.)*(3 if colorChain else 1.8)*(len({group[i]for i in card})==1)*resist[card[0]]))(len({color[i]for i in card})==1,.3*(color[card[0]]==1.1))))])(detect.getCardGroup()))[1])([self.servant[i]<6 and j and(t:=self.getHouguInfo(i,0))and self.stage>=min(t,self.stageTotal)for i,j in enumerate(detect.isHouguReady())],detect.isCardSealed(),[[.8,1.,1.1][i]for i in cardColor],[[1.,1.7,.6][i]for i in detect.getCardResist()],[i/10 for i in detect.getCardCriticalRate()]))
    def getSkillInfo(self,pos,skill,arg):return self.friendInfo[0][skill][arg]if self.friend[pos]and self.friendInfo[0][skill][arg]>=0 else self.skillInfo[self.orderChange[self.servant[pos]]][skill][arg]
    def getHouguInfo(self,pos,arg):return self.friendInfo[1][arg]if self.friend[pos]and self.friendInfo[1][arg]>=0 else self.houguInfo[self.orderChange[self.servant[pos]]][arg]
    def castServantSkill(self,pos,skill):
        key=('ASD','FGH','JKL')[pos][skill]
        fgoDevice.device.press(key)
        response=False
        timer=time.time()+1.2
        retry=0
        while True:
            detect=Detect(.2)
            if close:=detect.getSkillNoneClose():
                logger.warning(f'Skill {pos} {skill} Disabled')
                self.countDown[0][pos][skill]=999
                fgoDevice.device.touch(close)
                return
            if detect.isSkillCastFailed():
                self.countDown[0][pos][skill]=1
                fgoDevice.device.press('J')
                return
            if t:=detect.getSkillTargetCount():
                target=self.getSkillInfo(pos,skill,2)
                key=getSkillTargetKey(target,t)
                logger.info(f'Skill {pos+1}-{skill+1} target {target}, detected {t} choice(s), press {key}')
                fgoDevice.device.press(key)
                return
            if detect.isTurnBegin():
                if response:return
                if time.time()>timer:
                    retry+=1
                    if retry>3:raise ScriptStop(f'Skill {pos} {skill} Touch Failed')
                    logger.warning(f'Skill {pos} {skill} Touch Missed, Retry {retry}')
                    fgoDevice.device.press(key)
                    timer=time.time()+1.2
            else:response=True
    def castMasterSkill(self,skill):
        self.countDown[1][skill]=15
        fgoDevice.device.perform('Q'+'WER'[skill],(300,300))
        if self.masterSkill[skill][2]:
            if skill==2 and self.masterSkill[2][3]:
                if self.masterSkill[2][2]-1 not in self.servant or self.masterSkill[2][3]-1 in self.servant:return fgoDevice.device.perform('\xBB',(300,))
                p=self.servant.index(self.masterSkill[2][2]-1)
                fgoDevice.device.perform(('TYUIOP'[p],'TYUIOP'[self.masterSkill[2][3]-max(self.servant)+1],'Z'),(300,300,2600))
                self.orderChange[self.masterSkill[2][2]-1],self.orderChange[self.masterSkill[2][3]-1]=self.orderChange[self.masterSkill[2][3]-1],self.orderChange[self.masterSkill[2][2]-1]
                fgoDevice.device.perform('\x08',(2300,))
                while not Detect().isTurnBegin():pass
                self.friend=[Detect(.5).isServantFriend(0),Detect.cache.isServantFriend(1),Detect.cache.isServantFriend(2)]
                Detect.cache.setupServantDead(self.friend)
            elif t:=Detect(.5).getSkillTargetCount():fgoDevice.device.perform(getSkillTargetKey(self.masterSkill[skill][2],t),(300,))
class Turn:
    def __init__(self):
        self.stage=0
        self.stageTurn=0
        self.countDown=[[[0,0,0],[0,0,0],[0,0,0]],[0,0,0]]
    def __call__(self,turn):
        waitTurnBegin()
        previousStage=self.stage
        self.stage,self.stageTurn=[t:=Detect(.2).getStage(),1+self.stageTurn*(self.stage==t)]
        stable=getStableTurnDetect()
        if turn==1:
            stable.setupServantDead()
            self.stageTotal=stable.getStageTotal()
            self.servant=[(lambda x:(x,)+servantData.get(x,(0,0,0,0,(0,0),((0,0),(0,0),(0,0)))))(stable.getFieldServant(i))for i in range(3)]
        else:
            changed=[stable.isServantDead(i)for i in range(3)]
            if self.stage!=previousStage and all(changed):
                logger.warning('Ignored simultaneous servant changes during stage transition')
                stable.setupServantDead()
                changed=[False]*3
            for i in(i for i in range(3)if changed[i]):
                self.servant[i]=(lambda x:(x,)+servantData.get(x,(0,0,0,0,(0,0),((0,0),(0,0),(0,0)))))(stable.getFieldServant(i))
                self.countDown[0][i]=[0,0,0]
        logger.info(f'Turn {turn} Stage {self.stage} StageTurn {self.stageTurn} {[i[0]for i in self.servant]}')
        if self.stageTurn==1:self.enemy=[2,0,5][Detect.cache.setupEnemyGird()]
        self.enemy=[Detect.cache.getEnemyHp(i)for i in range(6)]
        self.dispatchSkill()
        fgoDevice.device.perform(' ',(2100,))
        detect,color=waitCardSelection()
        fgoDevice.device.perform(self.selectCard(detect,color),(300,300,2300,1300,6000))
    def dispatchSkill(self):
        self.countDown=[[[max(0,j-1)for j in i]for i in self.countDown[0]],[max(0,i-1)for i in self.countDown[1]]]
        while skill:=[(0,i,j)for i in range(3)for j in range(3)if not self.countDown[0][i][j]and self.servant[i][0]and self.servant[i][6][j][0]and Detect.cache.isSkillReady(i,j)]: # +[(1,i)for i in range(3)if self.countDown[1][i]==0]:
            for i in skill:
                if i[0]==0 and self.countDown[0][i[1]][i[2]]:continue
                if i[0]==0:
                    match self.servant[i[1]][6][i[2]]:
                        case 1,_:
                            self.castServantSkill(i[1],i[2],i[1]+1)
                            continue
                        case 2,p:
                            np=[Detect.cache.getFieldServantNp(i)if self.servant[i][0]else 100 for i in range(3)]
                            match p:
                                case 0:
                                    if any(i<100 for i in np):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 1:
                                    target=numpy.argmin(np)
                                    if np[target]<100:
                                        self.castServantSkill(i[1],i[2],target+1)
                                        continue
                                case 2:
                                    np[i[1]]=100
                                    if any(i<100 for i in np):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 3|4:
                                    if self.stageTurn>1:
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 5:
                                    if np[i[1]]<100:
                                        self.castServantSkill(i[1],i[2],i[1]+1)
                                        continue
                                case _:
                                    self.castServantSkill(i[1],i[2],0)
                                    continue
                        case 3,p:
                            np=[Detect.cache.getFieldServantNp(i)if self.servant[i][0]else 0 for i in range(3)]
                            match p:
                                case 0|3|4:
                                    if any(i>=100 for i in np):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 1:
                                    target=numpy.argmax(np)
                                    if np[target]>=100:
                                        self.castServantSkill(i[1],i[2],target+1)
                                        continue
                                case 2:
                                    np[i[1]]=0
                                    if any(i>=100 for i in np):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 5:
                                    if np[i[1]]>=100:
                                        self.castServantSkill(i[1],i[2],i[1]+1)
                                        continue
                                case _:
                                    self.castServantSkill(i[1],i[2],0)
                                    continue
                        case 4|5|6,_:
                            self.castServantSkill(i[1],i[2],0)
                            continue
                        case 7,p:
                            hp=[Detect.cache.getFieldServantHp(i)if self.servant[i][0]else 999999 for i in range(3)]
                            match p:
                                case 0:
                                    if any(i<6600 for i in hp):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 1:
                                    target=numpy.argmin(hp)
                                    if hp[target]<6600:
                                        self.castServantSkill(i[1],i[2],target+1)
                                        continue
                                case 2:
                                    hp[i[1]]=999999
                                    if any(i<6600 for i in hp):
                                        self.castServantSkill(i[1],i[2],0)
                                        continue
                                case 3|4:
                                    self.castServantSkill(i[1],i[2],0)
                                    continue
                                case 5:
                                    if hp[i[1]]<6600:
                                        self.castServantSkill(i[1],i[2],i[1]+1)
                                        continue
                                case _:
                                    self.castServantSkill(i[1],i[2],0)
                                    continue
                        case 8,_:
                            if any((lambda x:x[1]and x[0]==x[1])(Detect.cache.getEnemyNp(i))for i in range(6)):
                                self.castServantSkill(i[1],i[2],i[1]+1)
                                continue
                        case 9,_:
                            if any((lambda x:x[1]and x[0]==x[1])(Detect.cache.getEnemyNp(i))for i in range(6))or Detect.cache.getFieldServantHp(i[1])<3300:
                                self.castServantSkill(i[1],i[2],i[1]+1)
                                continue
                    self.countDown[0][i[1]][i[2]]=1
                else:...
    @logit(logger,logging.INFO)
    def selectCard(self,detect,cardColor):
        color,sealed,hougu,np,resist,critical,group=cardColor+[i[5][1]for i in self.servant],detect.isCardSealed(),detect.isHouguReady(),[detect.getFieldServantNp(i)<100 for i in range(3)],[[1,1.7,.6][i]for i in detect.getCardResist()],[i/10 for i in detect.getCardCriticalRate()],[next(j for j,k in enumerate(self.servant)if k[0]==i)for i in detect.getCardServant([i[0] for i in self.servant if i[0]])]+[0,1,2]
        houguTargeted,houguArea,houguSupport=[[j for j in range(3)if hougu[j]and self.servant[j][0]and self.servant[j][5][0]==i]for i in range(3)]
        houguArea=houguArea if self.stage==self.stageTotal or sum(i>0 for i in self.enemy)>1 and sum(self.enemy)>12000 else[]
        houguTargeted=houguTargeted if self.stage==self.stageTotal or max(self.enemy)>23000+8000*len(houguArea)else[]
        hougu=[i+5 for i in houguSupport+houguArea+houguTargeted]
        if self.stageTurn==1 or houguTargeted or self.enemy[self.target]==0:
            self.target=numpy.argmax(self.enemy)
            fgoDevice.device.perform('\x67\x68\x69\x64\x65\x66'[self.target],(500,))
        self.enemy=[max(0,i-18000*len(houguArea))for i in self.enemy]
        if any(self.enemy)and self.enemy[self.target]==0:self.target=next(i for i in range(5,-1,-1)if self.enemy[i])
        for _ in houguTargeted:
            self.enemy[self.target]=max(0,self.enemy[self.target]-48000)
            if any(self.enemy)and self.enemy[self.target]==0:self.target=next(i for i in range(5,-1,-1)if self.enemy[i])
        def evaluate(card):return(lambda chainError:(lambda colorChain:(lambda firstBonus:
                sum(
                    ((.3*bool(firstBonus&4)+.1*bool(firstBonus&1)+[1.,1.2,1.4][i]*[1,.8,1.1][color[j]])*(1+min(1,critical[j]+.2*bool(firstBonus&2)))+bool(colorChain==2))*resist[j]*(not sealed[j])
                    for i,j in enumerate(card)if j<5
                )
                +4*(len([i for i in self.enemy if i])>1)*(self.enemy[self.target]<20000)*sum(bool(i)for i in numpy.diff([group[i]for i in card if i<5]))
                +(1.8 if colorChain==-1 else 3)*(not chainError and len({group[i]for i in card})==1)*resist[card[0]]
                +2.3*(colorChain==0)*len({group[i]for i in card if i<5 and np[group[i]]})
                +3*(colorChain==1)
            )(7 if colorChain==3 else 1<<color[0]))(-1 if chainError else{(0,):0,(1):1,(2,):2,(0,1,2):3}.get(tuple(set(color[i]for i in card)),-1)))(any(sealed[i]for i in card if i<5))
        card=list(max(permutations(range(5),3-len(hougu)),key=lambda x:evaluate(hougu+list(x))))
        return''.join(['12345678'[i]for i in hougu+card+list({0,1,2,3,4}-set(card))])
    def castServantSkill(self,pos,skill,target):
        key=('ASD','FGH','JKL')[pos][skill]
        fgoDevice.device.press(key)
        response=False
        timer=time.time()+1.2
        retry=0
        while True:
            detect=Detect(.2)
            if close:=detect.getSkillNoneClose():
                logger.warning(f'Skill {pos} {skill} Disabled')
                self.countDown[0][pos][skill]=999
                fgoDevice.device.touch(close)
                break
            if detect.isSkillCastFailed():
                logger.warning(f'Skill {pos} {skill} Cast Failed')
                self.countDown[0][pos][skill]=1
                fgoDevice.device.press('J')
                break
            if t:=detect.getSkillTargetCount():
                f=self.servant[pos][6][skill][1]
                fgoDevice.device.perform(getSkillTargetKey(f-5 if f in{6,7,8}else target,t)+'\x08',(300,700))
                break
            if detect.isTurnBegin():
                if response:break
                if time.time()>timer:
                    retry+=1
                    if retry>3:raise ScriptStop(f'Skill {pos} {skill} Touch Failed')
                    logger.warning(f'Skill {pos} {skill} Touch Missed, Retry {retry}')
                    fgoDevice.device.press(key)
                    timer=time.time()+1.2
            else:response=True
        waitTurnBegin()
    def castMasterSkill(self,skill,target):
        self.countDown[1][skill]=15
        fgoDevice.device.perform('Q'+'WER'[skill],(300,300))
        if t:=Detect(.4).getSkillTargetCount():fgoDevice.device.perform(getSkillTargetKey(target,t),(300,))
        waitTurnBegin()
class Battle:
    def __init__(self,turnClass=Turn):
        self.turn=0
        self.turnProc=turnClass()
        self.rainbowBox=False
    def __call__(self):
        self.start=time.time()
        self.material={}
        while True:
            if Detect(0,.3).isTurnBegin():
                self.turn+=1
                self.turnProc(self.turn)
            elif Detect.cache.isSpecialDropSuspended():
                schedule.checkKizunaReisou()
                logger.warning('Kizuna Reisou')
                Detect.cache.save('fgoLog/SpecialDrop')
                fgoDevice.device.press('\x1B')
            elif not self.rainbowBox and Detect.cache.isSpecialDropRainbowBox():self.rainbowBox=True
            elif Detect.cache.isBattleFinished():
                logger.info('Battle Finished')
                self.material=Detect(.4).getMaterial()
                if self.rainbowBox:
                    logger.warning('Special Drop')
                    schedule.checkSpecialDrop()
                    Detect.cache.save('fgoLog/SpecialDrop')
                return True
            elif Detect.cache.isBattleDefeated():
                logger.warning('Battle Defeated')
                schedule.checkDefeated()
                return False
            fgoDevice.device.perform('\xBB\x08',(100,100))
    @property
    def result(self):
        return{
            'type':'Battle',
            'turn':self.turn,
            'time':time.time()-self.start,
            'material':self.material,
        }
class Main:
    teamIndex=0
    autoFormation=False
    friendClass=0
    def __init__(self,appleTotal=0,appleKind=0,battleClass=Battle):
        self.appleTotal=appleTotal
        self.appleKind=appleKind
        self.battleClass=battleClass
    @serialize(mutex)
    def __call__(self,questIndex=0,battleTotal=None):
        self.prepare()
        while True:
            self.battleProc=self.battleClass()
            while True:
                if Detect(.3,.3).isMainInterface():
                    if self.battleCount==battleTotal:return logger.info('Operation Unit Completed')
                    fgoDevice.device.press('84L'[questIndex])
                    questIndex=0
                    if Detect(1.2).isBattleContinue():fgoDevice.device.press('K')
                    elif Detect.cache.isSkillCastFailed():
                        fgoDevice.device.press('J')
                        return logger.info('No Storm Pot')
                    if Detect(.7,.3).isApEmpty()and not self.eatApple():return logger.info('Ap Empty')
                    self.chooseFriend()
                    while not Detect(0,.3).isBattleFormation():pass
                    if self.teamIndex and Detect.cache.getTeamIndex()+1!=self.teamIndex:fgoDevice.device.perform('\x70\x71\x72\x73\x74\x75\x76\x77\x78\x79\x7A\x7B\x7C\x7D\x7E'[self.teamIndex-1],(1000,))
                    if self.autoFormation:fgoDevice.device.perform('\xDEL ',(1000,1500,1000))
                    fgoDevice.device.perform(' M ',(2000,2000,10000))
                    break
                elif Detect.cache.isBattleContinue():
                    if self.battleCount==battleTotal:
                        fgoDevice.device.press('F')
                        return logger.info('Operation Unit Completed')
                    fgoDevice.device.press('K')
                    if Detect(.7,.3).isApEmpty()and not self.eatApple():return logger.info('Ap Empty')
                    self.chooseFriend()
                    schedule.sleep(6)
                    break
                elif Detect.cache.isSkillCastFailed():
                    fgoDevice.device.press('J')
                    return logger.info('No Storm Pot')
                elif Detect.cache.isTurnBegin():break
                elif Detect.cache.isAddFriend():fgoDevice.device.perform('X',(300,))
                elif Detect.cache.isSpecialDropSuspended():fgoDevice.device.perform('\x1B',(300,))
                fgoDevice.device.press('\xBB')
            self.battleCount+=1
            logger.info(f'Battle {self.battleCount}')
            if self.battleProc():
                battleResult=self.battleProc.result
                self.battleTurn+=battleResult['turn']
                self.battleTime+=battleResult['time']
                self.material={i:self.material.get(i,0)+battleResult['material'].get(i,0)for i in self.material|battleResult['material']}
                fgoDevice.device.perform(' '*10,(400,)*10)
            else:
                self.defeated+=1
                fgoDevice.device.perform('CIK',(500,500,500))
            schedule.checkStopLater()
        XDetect.clear()
        fuse.clear()
        gc.collect()
    def prepare(self):
        self.start=time.time()
        self.material={}
        self.battleCount=0
        self.battleTurn=0
        self.battleTime=0
        self.defeated=0
    @property
    def result(self):return{
            'type':'Main',
            'time':time.time()-self.start,
            'battle':self.battleCount,
            'defeated':self.defeated,
            'turnPerBattle':self.battleTurn/(self.battleCount-self.defeated)if self.battleCount-self.defeated else 0,
            'timePerBattle':self.battleTime/(self.battleCount-self.defeated)if self.battleCount-self.defeated else 0,
            'material':self.material,
        }
    @logit(logger,logging.INFO)
    def eatApple(self):
        if not self.appleTotal:return fgoDevice.device.press('Z')
        if self.appleKind==3:fgoDevice.device.perform('V',(600,))
        fgoDevice.device.perform('W4K48'[self.appleKind]+'L',(600,1200))
        self.appleTotal-=1
        logger.warning('Eat Apple')
        return self.appleTotal+1
    @logit(logger,logging.INFO)
    def chooseFriend(self):
        refresh=False
        while not Detect(0,.3).isChooseFriend():
            if Detect.cache.isNoFriend():
                if refresh:schedule.sleep(10)
                fgoDevice.device.perform('\xBAK',(500,1000))
                refresh=True
                continue
            if Detect.cache.isBattleFormation():return
        if self.friendClass > 0:
            fgoDevice.device.touch((90 + (self.friendClass - 1) * 68, 127))
            Detect(.5)
        if not friendImg.flush():return fgoDevice.device.press('8')
        while True:
            timer=time.time()
            while True:
                for i in(i for i,j in friendImg.items()if(lambda pos:pos and(fgoDevice.device.touch(pos),True)[-1])(Detect.cache.findFriend(j))):
                    ClassicTurn.friendInfo=(lambda r:(lambda p:[
                        [[-1 if p[i*4+j]=='X'else int(p[i*4+j],16)for j in range(4)]for i in range(3)],
                        [-1 if p[i+12]=='X'else int(p[i+12],16)for i in range(2)],
                    ])(r.group())if r else[[[-1,-1,-1,-1],[-1,-1,-1,-1],[-1,-1,-1,-1]],[-1,-1]])(re.match('([0-9X]{3}[0-9A-FX]){3}[0-9X][0-9A-FX]$',i.replace('-','')[-14:].upper()))
                    return i
                if Detect.cache.isFriendListEnd():break
                fgoDevice.device.swipe((400,600),(400,200))
                Detect(.4)
            if refresh:schedule.sleep(max(0,timer+10-time.time()))
            fgoDevice.device.perform('\xBAK',(500,1000))
            refresh=True
            while not Detect(.2).isChooseFriend():
                if Detect.cache.isNoFriend():
                    schedule.sleep(10)
                    fgoDevice.device.perform('\xBAK',(500,1000))
class Operation(list,Main):
    apLookup={i:j for i,j in zip(missionQuest,missionMat[0])}
    def __init__(self,data=(),*args,wait=True,**kwargs):
        list.__init__(self,data)
        Main.__init__(self,*args,**kwargs)
        self.wait=wait
    def __call__(self):
        super().prepare()
        if not self:super().__call__()
        while self:
            quest,times=self[0]
            del self[0]
            goto(quest)
            if self.wait:schedule.sleep(max(self.apLookup.get(quest,23)*times-Detect.cache.getAp(),0)*300)
            super().__call__(quest[-1],self.battleCount+times if times else None)
    def prepare(self):pass
    def getAp(self):return sum(self.apLookup.get(i,23)*j for i,j in self)
