import asyncio,json,os,time
from BRAINNET import BrainnetKernel
async def main():
 k=BrainnetKernel(); start=time.monotonic();task=asyncio.create_task(k.start())
 try:
  await asyncio.sleep(185)
  print(json.dumps({'seconds':round(time.monotonic()-start,2),'kernel_running':k.is_running,'rem':k.rem_engine is not None,'pdag':k.pdag is not None,'workers':k.bridge._running}),flush=True)
 finally:
  k.is_running=False
  await asyncio.wait_for(task,5)
  print(json.dumps({'shutdown':not k.bridge._running}),flush=True)
asyncio.run(main())
