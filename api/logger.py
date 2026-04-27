import os
from loguru import logger
from tqdm import tqdm
import sys

tqdm_stream = sys.stderr

def tqdm_sink(msg):
    tqdm.write(msg.rstrip(), file=tqdm_stream)
    tqdm_stream.flush()

logger.remove()
logger.add(tqdm_sink, colorize=True)
logger.add(os.getenv("CHAOXING_LOG_FILE", "/app/runtime/chaoxing.log"), rotation="10 MB", level=os.getenv("CHAOXING_LOG_LEVEL", "INFO"))
