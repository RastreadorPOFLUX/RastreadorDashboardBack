import httpx
import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ESPCommunicator:
    """Classe para comunicação com o ESP32 do rastreador solar"""
    
    def __init__(self, esp_ip: str, http_port: int = 80, ws_port: int = 81):
        self.esp_ip = esp_ip
        self.http_port = http_port
        self.ws_port = ws_port
        self.base_url = f"http://{esp_ip}:{http_port}"
        self.ws_url = f"ws://{esp_ip}:{ws_port}"
        self.timeout = httpx.Timeout(10.0)
        self.websocket = None
        self.is_websocket_connected = False
        self.last_data = {}
        
        # Configurações de reconexão
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        
    async def check_connection(self) -> bool:
        """Verificar se o ESP está acessível"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"ESP connection check failed: {e}")
            return False
    
    async def set_mode(self, mode: str) -> bool:
        """Configurar modo de operação do ESP"""
        try:
            payload = {"mode": mode}
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
    
    async def adjust_rtc(self, timestamp: int) -> bool:
        """Ajustar RTC do ESP"""
        try:
            payload = {"adjust": {"rtc": timestamp}}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/config",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    logger.info(f"ESP RTC adjusted to timestamp: {timestamp}")
                    return True
                else:
                    logger.error(f"Failed to adjust ESP RTC. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error adjusting ESP RTC: {e}")
            return False
    
    async def get_tracking_data(self) -> str:
        """Baixar dados de rastreamento CSV do ESP"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/pof-lux/tracking")
                if response.status_code == 200:
                    logger.info("Tracking data downloaded successfully")
                    return response.text
                else:
                    logger.error(f"Failed to download tracking data. Status: {response.status_code}")
                    return ""
        except Exception as e:
            logger.error(f"Error downloading tracking data: {e}")
            return ""
    
    async def clear_tracking_data(self) -> bool:
        """Limpar dados de rastreamento do ESP"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(f"{self.base_url}/pof-lux/clear_tracking")
                if response.status_code == 200:
                    logger.info("Tracking data cleared successfully")
                    return True
                else:
                    logger.error(f"Failed to clear tracking data. Status: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error clearing tracking data: {e}")
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
    
    async def get_weather_data(self, city: str, api_key: str) -> Dict[Any, Any]:
        """Obter dados climáticos via API externa (proxy para evitar CORS)"""
        try:
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(weather_url)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Transformar dados para o formato esperado
                    weather_data = {
                        "temperature": data["main"]["temp"],
                        "humidity": data["main"]["humidity"],
                        "pressure": data["main"]["pressure"],
                        "weather_description": data["weather"][0]["description"],
                        "cloudiness": data["clouds"]["all"]
                    }
                    
                    logger.info(f"Weather data retrieved for {city}")
                    return weather_data
                else:
                    logger.error(f"Failed to get weather data. Status: {response.status_code}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting weather data: {e}")
            return {}
    
    def get_last_data(self) -> Dict[Any, Any]:
        """Obter último conjunto de dados recebido"""
        return self.last_data.copy() if self.last_data else {}
    
    async def send_websocket_command(self, command: Dict[Any, Any]) -> bool:
        """Enviar comando via WebSocket para o ESP"""
        if not self.is_websocket_connected or not self.websocket:
            connected = await self.connect_websocket()
            if not connected:
                return False
        
        try:
            await self.websocket.send(json.dumps(command))
            logger.info(f"Command sent to ESP: {command}")
            return True
        except Exception as e:
            logger.error(f"Error sending command to ESP: {e}")
            self.is_websocket_connected = False
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Obter status das conexões"""
        return {
            "http_accessible": asyncio.run(self.check_connection()),
            "websocket_connected": self.is_websocket_connected,
            "last_data_timestamp": self.last_data.get("esp_clock", 0) if self.last_data else 0,
            "esp_ip": self.esp_ip,
            "base_url": self.base_url,
            "ws_url": self.ws_url
        }
    
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


# Função de conveniência para criar uma instância
def create_esp_communicator(esp_ip: str = "192.168.0.101") -> ESPCommunicator:
    """Criar uma instância do comunicador ESP com IP específico"""
    return ESPCommunicator(esp_ip=esp_ip) 