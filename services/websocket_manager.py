import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class WSConnectionManager:
    """Gerencia conexões WebSocket ativas de forma segura"""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Aceita uma nova conexão WebSocket e registra"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket conectado. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove conexão do manager"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket desconectado. Total: {len(self.active_connections)}")

    async def send_personal_json_message(self, message: dict, websocket: WebSocket):
        """Envia mensagem JSON para um WebSocket específico de forma segura"""
        try:
            if websocket.client_state.name != "CONNECTED":
                logger.warning("Tentativa de enviar mensagem para WebSocket desconectado")
                self.disconnect(websocket)
                return
            await websocket.send_json(message)
        except WebSocketDisconnect:
            logger.warning("WebSocketDisconnect detectado ao enviar mensagem")
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem pelo WebSocket: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Envia mensagem para todos os WebSockets ativos"""
        disconnected = []
        for connection in self.active_connections:
            try:
                if connection.client_state.name == "CONNECTED":
                    await connection.send_json(message)
                else:
                    disconnected.append(connection)
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem no broadcast: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

# Instância global do gerenciador
manager = WSConnectionManager()


class WebSocketHealthChecker:
    """Classe para monitorar a saúde das conexões WebSocket"""
    
    def __init__(self, ws_manager: WSConnectionManager, check_interval: int = 30):
        self.ws_manager = ws_manager
        self.check_interval = check_interval
        self.is_running = False
    
    async def start_health_check(self) -> None:
        """Iniciar verificação periódica de saúde das conexões"""
        self.is_running = True
        logger.info(f"Starting WebSocket health checker (interval: {self.check_interval}s)")
        
        while self.is_running:
            try:
                await self.ws_manager.cleanup_dead_connections()
                await self.ws_manager.ping_all_connections()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in WebSocket health check: {e}")
                await asyncio.sleep(5)  # Aguardar um pouco antes de tentar novamente
    
    def stop_health_check(self) -> None:
        """Parar verificação de saúde"""
        self.is_running = False
        logger.info("WebSocket health checker stopped")


# Instância global do health checker
health_checker = WebSocketHealthChecker(manager) 