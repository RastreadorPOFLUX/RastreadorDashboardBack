import httpx
import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ESPCommunicator:
    """Classe para comunicação com o ESP32 do rastreador solar"""
    
    def __init__(self, esp_ip: str, http_port: int = 80, ws_port: int = 82, device_id: str = None):
        self.esp_ip = esp_ip
        self.http_port = http_port
        self.ws_port = ws_port
        self.device_id = device_id
        self.base_url = f"http://{esp_ip}:{http_port}"
        self.ws_url = f"ws://{esp_ip}:{ws_port}"
        self.timeout = httpx.Timeout(10.0)
        self.websocket = None
        self.is_websocket_connected = False
        self.last_data = {}
        self.last_connection_check = 0
        self.connection_check_interval = 5  # segundos
        
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.connection_status = {"connected": False, "last_error": None}

        # 🚀 Tentativa automática de conexão ao criar a instância
        asyncio.create_task(self._auto_init_connect())

    async def _auto_init_connect(self):
        """Tenta conexão HTTP e WebSocket automaticamente após instanciar."""
        if await self.check_connection():
            if await self.connect_websocket():
                logger.info(f"WebSocket inicializado automaticamente para {self.esp_ip}")
        else:
            logger.warning(f"Não foi possível conectar automaticamente ao ESP ({self.esp_ip}) no init.")

    async def _handle_connection_failure(self):
        logger.warning(f"Falha de conexão com ESP ({self.esp_ip}). Tentando reconectar...")
        for attempt in range(self.max_reconnect_attempts):
            await asyncio.sleep(self.reconnect_delay)
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.base_url}/")
                    if response.status_code == 200:
                        logger.info(f"Reconexão bem-sucedida com ESP ({self.esp_ip})")
                        self.connection_status["connected"] = True
                        return True
            except Exception as e:
                logger.error(f"Tentativa {attempt + 1} de reconexão falhou: {str(e)}")
        logger.error(f"Todas as tentativas de reconexão falharam para ESP ({self.esp_ip})")
        return False

    async def check_connection(self) -> bool:
        """Verificar se o ESP está acessível via HTTP GET na raiz."""
        self.last_connection_check = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/")
                if response.status_code == 200:
                    self.connection_status["connected"] = True
                    self.connection_status["last_error"] = None
                    logger.info(f"Conexão HTTP com ESP bem-sucedida: {self.base_url}")
                    return True
                else:
                    logger.error(f"Erro HTTP com ESP: Status {response.status_code}")
                    self.connection_status["connected"] = False
                    self.connection_status["last_error"] = f"Status code: {response.status_code}"
                    return False
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão HTTP com ESP: {e}")
            self.connection_status["connected"] = False
            self.connection_status["last_error"] = str(e)
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao checar conexão com ESP: {e}")
            self.connection_status["connected"] = False
            self.connection_status["last_error"] = str(e)
            return False

    async def set_mode(self, mode: str, manualSetpoint: int) -> bool:
        try:
            payload = {"mode": mode,
                       "manual_setpoint": manualSetpoint,
                       "adjust": {"rtc": int(datetime.now().timestamp())}}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/config",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error setting ESP mode: {e}")
            return False

    async def connect_websocket(self) -> bool:
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.is_websocket_connected = True
            logger.info("ESP WebSocket connectado com sucesso")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar com o ESP WebSocket: {e}")
            self.is_websocket_connected = False
            return False

    async def disconnect_websocket(self) -> None:
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("ESP WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting ESP WebSocket: {e}")
        self.is_websocket_connected = False
        self.websocket = None

    async def start_websocket_listener(self, data_callback=None) -> None:
        reconnect_attempts = 0
        logger.info("Iniciando listener WebSocket do ESP32...")
        while True:
            try:
                if not self.is_websocket_connected:
                    connected = await self.connect_websocket()
                    if not connected:
                        reconnect_attempts += 1
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                reconnect_attempts = 0
                while self.is_websocket_connected:
                    try:
                        raw_data = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                        data = json.loads(raw_data)
                        self.last_data = data
                        if data_callback:
                            await data_callback(data)
                    except asyncio.TimeoutError:
                        pass
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}")
                self.is_websocket_connected = False
                reconnect_attempts += 1
                await asyncio.sleep(self.reconnect_delay)

    async def update_esp_config(self, new_ip: str, device_id: str = None, new_http_port: int = 80, new_ws_port: int = 82) -> bool:
        old_ip = self.esp_ip
        self.esp_ip = new_ip
        if device_id:
            self.device_id = device_id
        self.http_port = new_http_port
        self.ws_port = new_ws_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        self.ws_url = f"ws://{new_ip}:{new_ws_port}"
        
        if self.is_websocket_connected:
            await self.disconnect_websocket()
        
        if await self.check_connection():
            logger.info(f"ESP configuração atualizada e conectada: {self.base_url}, {self.ws_url}")
            if await self.connect_websocket():
                logger.info("WebSocket reiniciado automaticamente após update_esp_config")
                return True
        
        logger.error(f"Falha ao conectar com novo IP {new_ip}, revertendo para {old_ip}")
        self.esp_ip = old_ip
        self.base_url = f"http://{old_ip}:{self.http_port}"
        self.ws_url = f"ws://{old_ip}:{self.ws_port}"
        return False
    
    def get_last_data(self) -> Dict[Any, Any]:
        """
        Retorna o último conjunto de dados recebido via WebSocket.
        Se não houver dados recentes, tenta fazer uma leitura imediata.
        """
        # Dados no cache
        if self.last_data:
            return self.last_data

        # Tentativa de leitura imediata
        if self.is_websocket_connected and self.websocket:
            try:
                loop = asyncio.get_event_loop()
                raw_data = loop.run_until_complete(
                    asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                )
                data = json.loads(raw_data)
                self.last_data = data
                return self.last_data
            except asyncio.TimeoutError:
                logger.warning("WebSocket sem dados no tempo limite")
            except json.JSONDecodeError as e:
                logger.error(f"JSON inválido recebido do ESP: {e}")
            except Exception as e:
                logger.error(f"Erro ao tentar receber dados do WebSocket: {e}")

        return {}

def create_esp_communicator(esp_ip: str = "192.168.0.101") -> ESPCommunicator:
    return ESPCommunicator(esp_ip=esp_ip)