import httpx
import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ESPCommunicator:
    """Classe para comunicação com o ESP32 do rastreador solar"""
    
    def __init__(self, esp_ip: str, http_port: int = 80, ws_port: int = 81, device_id: str = None):
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
        
        # Configurações de reconexão
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.connection_status = {"connected": False, "last_error": None}
        
    async def _handle_connection_failure(self):
        """Gerenciar falhas de conexão e tentar reconexão"""
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
        """Verificar se o ESP está acessível via HTTP GET na raiz"""
        current_time = time.time()
        
        # Evitar checagens muito frequentes
        if current_time - self.last_connection_check < self.connection_check_interval:
            return self.connection_status["connected"]
            
        self.last_connection_check = current_time
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/")
                if response.status_code == 200:
                    self.connection_status["connected"] = True
                    self.connection_status["last_error"] = None
                    return True
                else:
                    raise httpx.RequestError(f"Status code: {response.status_code}")
                    
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão HTTP com ESP: {e}")
            self.connection_status["connected"] = False
            self.connection_status["last_error"] = str(e)
            await self._handle_connection_failure()
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao checar conexão com ESP: {e}")
            self.connection_status["connected"] = False
            self.connection_status["last_error"] = str(e)
            await self._handle_connection_failure()
            return False
    
    async def set_mode(self, mode: str, manualSetpoint: int) -> bool:
        """Configurar modo de operação do ESP"""
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
                if response.status_code == 200:
                    logger.info(f"ESP mode set to: {mode}")
                    return True
                else:
                    logger.error(f"Failed to set ESP mode. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error setting ESP mode: {e}")
            return False
    
    async def connect_websocket(self) -> bool:
        """Conectar ao WebSocket do ESP"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.is_websocket_connected = True
            logger.info("ESP WebSocket connected successfully")
            return True
        except Exception as e:
            logger.error(f"Error connecting to ESP WebSocket: {e}")
            self.is_websocket_connected = False
            return False
    
    async def disconnect_websocket(self) -> None:
        """Desconectar do WebSocket do ESP"""
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("ESP WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting ESP WebSocket: {e}")
        
        self.is_websocket_connected = False
        self.websocket = None
    
    async def listen_websocket_data(self) -> Optional[Dict[Any, Any]]:
        """Escutar dados do WebSocket do ESP"""
        if not self.is_websocket_connected or not self.websocket:
            await self.connect_websocket()
        
        try:
            # Aguardar dados com timeout
            raw_data = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            data = json.loads(raw_data)
            self.last_data = data
            return data
        except asyncio.TimeoutError:
            logger.warning("WebSocket timeout - no data received")
            return self.last_data if self.last_data else None
        except websockets.exceptions.ConnectionClosed:
            logger.warning("ESP WebSocket connection closed")
            self.is_websocket_connected = False
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received from ESP: {e}")
            return None
        except Exception as e:
            logger.error(f"Error listening to ESP WebSocket: {e}")
            self.is_websocket_connected = False
            return None
    
    async def start_websocket_listener(self, data_callback=None) -> None:
        """Iniciar escuta contínua do WebSocket do ESP"""
        reconnect_attempts = 0
        
        while reconnect_attempts < self.max_reconnect_attempts:
            try:
                if not self.is_websocket_connected:
                    connected = await self.connect_websocket()
                    if not connected:
                        reconnect_attempts += 1
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                
                # Reset contador de reconexão em caso de sucesso
                reconnect_attempts = 0
                
                while self.is_websocket_connected:
                    data = await self.listen_websocket_data()
                    if data and data_callback:
                        await data_callback(data)
                    
                    # Pequena pausa para não sobrecarregar
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}")
                self.is_websocket_connected = False
                reconnect_attempts += 1
                await asyncio.sleep(self.reconnect_delay)
        
        logger.error(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached")
    
    def get_last_data(self) -> Dict[Any, Any]:
        """Obter último conjunto de dados recebido, tentando atualizar via WebSocket se possível"""
        # Se o WebSocket está conectado, tenta receber dados novos
        if self.is_websocket_connected and self.websocket:
            try:
                # Tenta receber dados com timeout curto
                import asyncio
                loop = asyncio.get_event_loop()
                raw_data = loop.run_until_complete(asyncio.wait_for(self.websocket.recv(), timeout=1.0))
                data = json.loads(raw_data)
                self.last_data = data
            except Exception as e:
                logger.warning(f"Não foi possível atualizar dados via WebSocket: {e}")
        return self.last_data.copy() if self.last_data else {}
    
    async def update_esp_config(self, new_ip: str, device_id: str = None, new_http_port: int = 80, new_ws_port: int = 81) -> bool:
        """Atualizar configurações de IP e porta do ESP e tentar estabelecer conexão"""
        old_ip = self.esp_ip
        self.esp_ip = new_ip
        if device_id:
            self.device_id = device_id
        self.http_port = new_http_port
        self.ws_port = new_ws_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        self.ws_url = f"ws://{new_ip}:{new_ws_port}"
        
        # Desconectar WebSocket existente se houver
        if self.is_websocket_connected:
            await self.disconnect_websocket()
        
        # Tentar estabelecer conexão com o novo IP
        if await self.check_connection():
            logger.info(f"ESP configuração atualizada e conectada: {self.base_url}, {self.ws_url}")
            # Tentar reconectar WebSocket
            if await self.connect_websocket():
                return True
        
        # Reverter para o IP antigo se a conexão falhar
        logger.error(f"Falha ao conectar com novo IP {new_ip}, revertendo para {old_ip}")
        self.esp_ip = old_ip
        self.base_url = f"http://{old_ip}:{self.http_port}"
        self.ws_url = f"ws://{old_ip}:{self.ws_port}"
        return False
    
    async def ping_esp(self) -> bool:
        """Fazer ping no ESP para verificar conectividade"""
        try:
            start_time = time.time()
            is_connected = await self.check_connection()
            response_time = (time.time() - start_time) * 1000  # em ms
            
            if is_connected:
                logger.info(f"ESP ping successful ({response_time:.1f}ms)")
            else:
                logger.warning("ESP ping failed")
            
            return is_connected
        except Exception as e:
            logger.error(f"Error pinging ESP: {e}")
            return False
    
    def update_esp_config(self, new_ip: str, new_http_port: int = 80, new_ws_port: int = 81) -> None:
        """Atualizar configurações de IP e porta do ESP"""
        self.esp_ip = new_ip
        self.http_port = new_http_port
        self.ws_port = new_ws_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        self.ws_url = f"ws://{new_ip}:{new_ws_port}"
        
        # Desconectar WebSocket existente
        if self.is_websocket_connected:
            asyncio.create_task(self.disconnect_websocket())
        
        logger.info(f"ESP configuration updated: {self.base_url}, {self.ws_url}")
    
    async def auto_connect(self):
        """Tenta conectar automaticamente ao ESP32 via HTTP e WebSocket"""
        # Tenta conexão HTTP
        http_ok = await self.check_connection()
        if not http_ok:
            logger.error(f"Não foi possível conectar ao ESP32 via HTTP: {self.base_url}")
            return False
        # Tenta conexão WebSocket
        ws_ok = await self.connect_websocket()
        if not ws_ok:
            logger.error(f"Não foi possível conectar ao ESP32 via WebSocket: {self.ws_url}")
            return False
        logger.info(f"Conexão automática com ESP32 bem-sucedida: {self.esp_ip}")
        return True

    async def ensure_connection(self):
        """Garante que a conexão com o ESP32 está ativa, tentando reconectar se necessário"""
        if not await self.check_connection():
            logger.warning("Tentando reconexão HTTP com ESP32...")
            await self._handle_connection_failure()
        if not self.is_websocket_connected:
            logger.warning("Tentando reconexão WebSocket com ESP32...")
            await self.connect_websocket()

    def is_connected(self) -> bool:
        """Retorna True se ambas conexões (HTTP e WebSocket) estão ativas"""
        return self.connection_status["connected"] and self.is_websocket_connected

    async def get_angles_from_esp(self) -> dict:
        """Buscar os ângulos diretamente do ESP via HTTP GET /angles"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/angles")
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Dados de ângulos recebidos do ESP: {data}")
                    return data
                else:
                    logger.error(f"Falha ao obter ângulos do ESP. Status: {response.status_code}")
                    return {"sun_position": 0.0, "lens_angle": 0.0, "manual_setpoint": 0.0}
        except Exception as e:
            logger.error(f"Erro ao buscar ângulos do ESP: {e}")
            return {"sun_position": 0.0, "lens_angle": 0.0, "manual_setpoint": 0.0}
        
    
    async def get_pid_from_esp(self) -> dict:
        """Buscar as constantes PID diretamente do ESP via HTTP GET /pidParameters"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/pidParameters")
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Dados dos parâmetros PID recebidos do ESP: {data}")
                    return data
                else:
                    logger.error(f"Falha ao obter parâmetros PID. Status: {response.status_code}")
                    return {"kp": 0.0, "ki": 0.0, "kd": 0.0}
        except Exception as e:
            logger.error(f"Erro ao buscar parâmetros PID do ESP: {e}")
            return {"kp": 0.0, "ki": 0.0, "kd": 0.0}
        
    async def set_pid_parameters(self, kp: float, ki:float, kd:float) -> bool:
        """Configurar os parâmetros PID do ESP via HTTP PATCH /config"""
        try:
            payload = {"adjust":{"kp": kp, "ki": ki, "kd": kd}}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/config/pidParameters",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    logger.info(f"Parâmetros PID atualizados: {payload}")
                    return True
                else:
                    logger.error(f"Falha ao atualizar parâmetros PID. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao atualizar parâmetros PID: {e}")
            return False
        

    async def get_motor_power_from_esp(self) -> dict:
        """Buscar a potência do motor diretamente do ESP via HTTP GET /motor"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/motor")
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Dados da potência do motor recebidos do ESP: {data}")
                    return data
                else:
                    logger.error(f"Falha ao obter a potência do motor. Status: {response.status_code}")
                    return {"pwm": 0}
        except Exception as e:
            logger.error(f"Erro ao buscar a potência do motor do ESP: {e}")
            return {"pwm": 0}

    async def get_tracking_data(self) -> str:
        """Buscar os dados de tracking diretamente do ESP via HTTP GET /tracking"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/tracking")
                
                if response.status_code == 200:
                    csv_data = response.text
                    
                    # Verificar se os dados não estão vazios e têm formato correto
                    if len(csv_data.strip()) == 0:
                        logger.warning("Arquivo de tracking vazio")
                        return ""
                    
                    # Verificar se tem o cabeçalho esperado
                    if not csv_data.startswith("Channel name,Timestamp,Value"):
                        logger.warning("Formato de arquivo de tracking inválido")
                        return ""
                    
                    logger.info(f"Dados de tracking recebidos: {len(csv_data)} bytes, {len(csv_data.splitlines())} linhas")
                    return csv_data
                else:
                    logger.error(f"Falha ao obter dados de tracking. Status: {response.status_code}")
                    return ""
        except Exception as e:
            logger.error(f"Erro ao buscar dados de tracking do ESP: {e}")
            return ""
    

# Função de conveniência para criar uma instância
def create_esp_communicator(esp_ip: str = "192.168.0.101") -> ESPCommunicator:
    """Criar uma instância do comunicador ESP com IP específico"""
    return ESPCommunicator(esp_ip=esp_ip)