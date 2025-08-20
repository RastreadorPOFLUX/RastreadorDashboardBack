import httpx
import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, Callable
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
        self.ws_url = f"ws://{esp_ip}:{ws_port}"  # CORRIGIDO: porta 82
        self.timeout = httpx.Timeout(10.0)
        self.websocket = None
        self.is_websocket_connected = False
        self.last_data = {}
        self.last_connection_check = 0
        self.connection_check_interval = 5  # segundos
        
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.connection_status = {"connected": False, "last_error": None}

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

    async def set_mode(self, mode: str, manual_setpoint: float = 0.0) -> bool:
        """Define o modo de operação do ESP32"""
        try:
            payload = {
                "mode": mode,
                "manual_setpoint": manual_setpoint,
                "adjust": {"rtc": int(datetime.now().timestamp())}
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/config",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                success = response.status_code == 200
                if success:
                    logger.info(f"Modo alterado para {mode}, setpoint: {manual_setpoint}")
                else:
                    logger.error(f"Falha ao alterar modo: HTTP {response.status_code}")
                return success
        except Exception as e:
            logger.error(f"Erro ao definir modo do ESP: {e}")
            return False

    async def connect_websocket(self) -> bool:
        """Conecta ao WebSocket do ESP32"""
        try:
            self.websocket = await websockets.connect(
                self.ws_url, 
                ping_interval=20,  # Mantém conexão ativa
                ping_timeout=10,
                close_timeout=1
            )
            self.is_websocket_connected = True
            logger.info(f"WebSocket conectado com sucesso: {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar com WebSocket do ESP: {e}")
            self.is_websocket_connected = False
            return False

    async def disconnect_websocket(self) -> None:
        """Desconecta do WebSocket"""
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("WebSocket desconectado")
            except Exception as e:
                logger.error(f"Erro ao desconectar WebSocket: {e}")
        self.is_websocket_connected = False
        self.websocket = None

    async def start_websocket_listener(self, data_callback: Optional[Callable] = None) -> None:
        """Inicia listener para dados do WebSocket com reconexão automática"""
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        
        logger.info("Iniciando listener WebSocket do ESP32...")
        
        while True:
            try:
                # Verifica se precisa reconectar
                if not self.is_websocket_connected or self.websocket is None:
                    if reconnect_attempts >= max_reconnect_attempts:
                        logger.error("Máximo de tentativas de reconexão atingido")
                        break
                    
                    logger.info(f"Tentando conectar WebSocket (tentativa {reconnect_attempts + 1})...")
                    connected = await self.connect_websocket()
                    if not connected:
                        reconnect_attempts += 1
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                    reconnect_attempts = 0
                
                # Escuta por mensagens
                try:
                    raw_data = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    data = json.loads(raw_data)
                    self.last_data = data
                    
                    if data_callback:
                        await data_callback(data)
                        
                except asyncio.TimeoutError:
                    # Timeout normal, verifica se conexão ainda está ativa
                    try:
                        await self.websocket.ping()
                    except:
                        logger.warning("Conexão WebSocket inativa, reconectando...")
                        self.is_websocket_connected = False
                        continue
                        
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Conexão WebSocket fechada, reconectando...")
                    self.is_websocket_connected = False
                    continue
                    
            except Exception as e:
                logger.error(f"Erro no listener WebSocket: {e}")
                self.is_websocket_connected = False
                reconnect_attempts += 1
                await asyncio.sleep(self.reconnect_delay)

    async def get_angles(self) -> Optional[Dict]:
        """Obtém ângulos atuais via HTTP"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/angles")
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Erro ao obter ângulos: {e}")
        return None

    async def get_pid_parameters(self) -> Optional[Dict]:
        """Obtém parâmetros PID atuais via HTTP"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/pidParameters")
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Erro ao obter parâmetros PID: {e}")
        return None

    async def get_motor_status(self) -> Optional[Dict]:
        """Obtém status do motor via HTTP"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/motor")
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Erro ao obter status do motor: {e}")
        return None

    async def clear_tracking_data(self) -> bool:
        """Limpa dados de tracking"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(f"{self.base_url}/clear_tracking")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Erro ao limpar dados de tracking: {e}")
            return False

    async def update_esp_config(self, new_ip: str, device_id: str = None, 
                               new_http_port: int = 80, new_ws_port: int = 82) -> bool:
        """Atualiza configuração de conexão com o ESP"""
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
        
        # Testa nova conexão
        if await self.check_connection():
            logger.info(f"Configuração atualizada e conectada: {self.base_url}")
            return True
        
        logger.error(f"Falha ao conectar com novo IP {new_ip}, revertendo para {old_ip}")
        self.esp_ip = old_ip
        self.base_url = f"http://{old_ip}:{self.http_port}"
        self.ws_url = f"ws://{old_ip}:{self.ws_port}"
        return False

    def get_last_data(self) -> Dict:
        """Retorna o último conjunto de dados recebido via WebSocket"""
        return self.last_data.copy()

async def create_esp_communicator(esp_ip: str = "192.168.0.101") -> ESPCommunicator:
    """Factory function para criar e inicializar communicator"""
    communicator = ESPCommunicator(esp_ip=esp_ip)
    
    # Tenta conexão inicial
    if await communicator.check_connection():
        logger.info(f"Conectado ao ESP32 em {esp_ip}")
    else:
        logger.warning(f"Não foi possível conectar ao ESP32 em {esp_ip}")
    
    return communicator

# Exemplo de uso
async def example_usage():
    # Cria communicator
    esp = await create_esp_communicator("192.168.0.101")
    
    # Define callback para dados WebSocket
    async def handle_esp_data(data: Dict):
        print(f"Dados recebidos: {data}")
    
    # Inicia listener em background
    listener_task = asyncio.create_task(esp.start_websocket_listener(handle_esp_data))
    
    # Exemplo: alterar para modo manual
    await esp.set_mode("manual", 15.5)
    
    # Mantém programa rodando
    try:
        await asyncio.Future()  # Executa forever
    except KeyboardInterrupt:
        await esp.disconnect_websocket()
        listener_task.cancel()

if __name__ == "__main__":
    asyncio.run(example_usage())