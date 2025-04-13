import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from amplitude import Amplitude, BaseEvent 
from config import settings


amplitude_client = Amplitude(api_key=settings.AMPLITUDE_API_KEY)
amplitude_executor = ThreadPoolExecutor(max_workers=4)  
amplitude_lock = Lock() 


def amplitude_sdk(user_id: str, event_type: str, event_props: dict = None):
    """Отправляет событие в Amplitude"""
    event = BaseEvent(
        event_type=event_type,  
        user_id=str(user_id),   
        event_properties=event_props  
    )
    
    with amplitude_lock:
        amplitude_client.track(event)
        
        
async def async_amplitude_track(user_id: str, event_type: str, event_props: dict = None):
    """Передает задачу в поток, чтобы не блокировать бота"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        amplitude_executor,           
        amplitude_sdk,         
        user_id, event_type, event_props  
    )
