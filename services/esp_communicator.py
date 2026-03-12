import httpx
import asyncio
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
    
    def __init__(self, esp_ip: str, http_port: int = 80, device_id: str = None):
        self.esp_ip = esp_ip
        self.http_port = http_port
        self.device_id = device_id
        self.base_url = f"http://{esp_ip}:{http_port}"
        self.timeout = httpx.Timeout(10.0)
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
    
    def get_last_data(self) -> Dict[Any, Any]:
        """Obter último conjunto de dados recebido"""
        return self.last_data.copy() if self.last_data else {}
    
    async def update_esp_config(self, new_ip: str, device_id: str = None, 
                               new_http_port: int = 80) -> bool:
        """Atualiza configuração de conexão com o ESP"""
        old_ip = self.esp_ip
        self.esp_ip = new_ip
        if device_id:
            self.device_id = device_id
        self.http_port = new_http_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        
        # Testa nova conexão
        if await self.check_connection():
            logger.info(f"Configuração atualizada e conectada: {self.base_url}")
            return True
        
        logger.error(f"Falha ao conectar com novo IP {new_ip}, revertendo para {old_ip}")
        self.esp_ip = old_ip
        self.base_url = f"http://{old_ip}:{self.http_port}"
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
    
    def update_esp_config_sync(self, new_ip: str, new_http_port: int = 80) -> None:
        """Atualizar configurações de IP e porta do ESP"""
        self.esp_ip = new_ip
        self.http_port = new_http_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        
        logger.info(f"ESP configuration updated: {self.base_url}")
    
    async def auto_connect(self):
        """Tenta conectar automaticamente ao ESP32 via HTTP"""
        # Tenta conexão HTTP
        http_ok = await self.check_connection()
        if not http_ok:
            logger.error(f"Não foi possível conectar ao ESP32 via HTTP: {self.base_url}")
            return False
        logger.info(f"Conexão automática com ESP32 bem-sucedida: {self.esp_ip}")
        return True

    async def ensure_connection(self):
        """Garante que a conexão com o ESP32 está ativa, tentando reconectar se necessário"""
        if not await self.check_connection():
            logger.warning("Tentando reconexão HTTP com ESP32...")
            await self._handle_connection_failure()

    def is_connected(self) -> bool:
        """Retorna True se conexão HTTP está ativa"""
        return self.connection_status["connected"]

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
        

    async def get_sensors_data_from_esp(self) -> dict:
        """Buscar os dados dos sensores diretamente do ESP via HTTP GET /sensors"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/sensors")
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Dados dos sensores recebidos do ESP: {data}")
                    return data
                else:
                    logger.error(f"Falha ao obter dados dos sensores. Status: {response.status_code}")
                    return {"pyranometer": 0.0, "photodetector": 0.0}
        except Exception as e:
            logger.error(f"Erro ao buscar dados dos sensores do ESP: {e}")
            return {"pyranometer": 0.0, "photodetector": 0.0}
    
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
                    
                    logger.info(f"Dados de tracking recebidos: {len(csv_data)} bytes, {len(csv_data.splitlines())} linhas")
                    return csv_data
                else:
                    logger.error(f"Falha ao obter dados de tracking. Status: {response.status_code}")
                    return ""
        except Exception as e:
            logger.error(f"Erro ao buscar dados de tracking do ESP: {e}")
            return ""
        
    async def clear_tracking_data(self) -> bool:
        """Limpar dados de tracking no ESP32 via HTTP DELETE /clear_tracking"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(f"{self.base_url}/clear_tracking")
                if response.status_code == 200:
                    logger.info("Dados de tracking limpos com sucesso")
                    return True
                else:
                    logger.error(f"Falha ao limpar dados de tracking. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao limpar dados de tracking: {e}")
            return False

# Função de conveniência para criar uma instância
def create_esp_communicator(esp_ip: str = "192.168.0.101") -> ESPCommunicator:
    """Criar uma instância do comunicador ESP com IP específico"""
    return ESPCommunicator(esp_ip=esp_ip)