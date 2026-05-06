from pponnxcr import TextSystem
from fgoLogging import getLogger,logit
logger=getLogger('Ocr')
class Ocr(TextSystem):
    @logit(logger)
    def __call__(self,img):return super().ocr_single_line(img)[0]
    def ocrInt(self,img):
        res=self(img)
        for i,j in (('I','1'),('l','1'),('i','1'),('|','1'),('!','1'),('L','1'),('O','0'),('o','0')):res=res.replace(i,j)
        import re
        res=re.sub(r'[^\d\s]',' ',res)
        return next((int(i)for i in res.split()if i.isdigit()),0)
    def ocrText(self,img):return self(img)
    @logit(logger,transform=lambda x:'|'.join(x))
    def ocrArea(self,img):return[i.text for i in self.detect_and_ocr(img)]
