import httpx
import asyncio
import logging
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
        self.last_connection_check = 0
        self.connection_check_interval = 5  # segundos
        
        # Configurações de reconexão
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.connection_status = {"connected": False, "last_error": None}
        
    async def _try_connect(self):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/")
            if response.status_code == 200:
                return response
            else:
                raise httpx.RequestError(f"Conexão falhou. Status: {response.status_code}")
        
    async def handle_connection_failure(self):
        """Gerenciar falhas de conexão e tentar reconexão"""
        logger.warning(f"Falha de conexão com ESP ({self.esp_ip}). Tentando reconectar...")
        
        for attempt in range(self.max_reconnect_attempts):
            await asyncio.sleep(self.reconnect_delay)
            try:
                await self._try_connect()
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
            await self._try_connect()
            self.connection_status["connected"] = True
            self.connection_status["last_error"] = None
            return True
                    
        except httpx.RequestError or Exception as e:
            logger.error(f"Erro de conexão HTTP com ESP: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao checar conexão com ESP: {e}")
        self.connection_status["connected"] = False
        self.connection_status["last_error"] = str(e)
        response = await self.handle_connection_failure()            
        return response
    
    def update_esp_config(self, new_ip: str, new_http_port: int = 80) -> None:
        """Atualizar configurações de IP e porta do ESP"""
        self.esp_ip = new_ip
        self.http_port = new_http_port
        self.base_url = f"http://{new_ip}:{new_http_port}"
        
        logger.info(f"Configuração do ESP atualizada: {self.base_url}")


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
                    logger.error(f"Falha ao configurar modo do ESP. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao configurar modo do ESP: {e}")
            return False

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
