from fastapi import WebSocket
from typing import List, Dict, Any
import json
import asyncio
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WSConnectionManager:
    """Gerenciador de conexões WebSocket para comunicação em tempo real"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_count = 0
    
    async def connect(self, websocket: WebSocket) -> None:
        """Aceitar nova conexão WebSocket"""
        try:
            await websocket.accept()
            self.active_connections.append(websocket)
            self.connection_count += 1
            logger.info(f"New WebSocket connection. Total connections: {len(self.active_connections)}")
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {e}")
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Remover conexão WebSocket"""
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Enviar mensagem de texto para uma conexão específica"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending text message: {e}")
            self.disconnect(websocket)
    
    async def send_personal_json_message(self, message: Dict[Any, Any], websocket: WebSocket) -> None:
        """Enviar mensagem JSON para uma conexão específica"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending JSON message: {e}")
            self.disconnect(websocket)
    
    async def broadcast_text(self, message: str) -> None:
        """Enviar mensagem de texto para todas as conexões ativas"""
        if not self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting text message: {e}")
                disconnected.append(connection)
        
        # Remover conexões desconectadas
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_json(self, message: Dict[Any, Any]) -> None:
        """Enviar mensagem JSON para todas as conexões ativas"""
        if not self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting JSON message: {e}")
                disconnected.append(connection)
        
        # Remover conexões desconectadas
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_to_all_except(self, message: Dict[Any, Any], exclude_websocket: WebSocket) -> None:
        """Enviar mensagem para todas as conexões exceto uma específica"""
        if not self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections:
            if connection != exclude_websocket:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to all except one: {e}")
                    disconnected.append(connection)
        
        # Remover conexões desconectadas
        for conn in disconnected:
            self.disconnect(conn)
    
    def get_active_connections_count(self) -> int:
        """Retornar número de conexões ativas"""
        return len(self.active_connections)
    
    def is_connected(self) -> bool:
        """Verificar se há pelo menos uma conexão ativa"""
        return len(self.active_connections) > 0
    
    async def ping_all_connections(self) -> None:
        """Enviar ping para todas as conexões para verificar se estão ativas"""
        if not self.active_connections:
            return
        
        ping_message = {"type": "ping", "timestamp": int(asyncio.get_event_loop().time())}
        await self.broadcast_json(ping_message)
    
    async def send_system_notification(self, notification_type: str, message: str) -> None:
        """Enviar notificação do sistema para todas as conexões"""
        notification = {
            "type": "system_notification",
            "notification_type": notification_type,
            "message": message,
            "timestamp": int(asyncio.get_event_loop().time())
        }
        await self.broadcast_json(notification)
    
    async def cleanup_dead_connections(self) -> None:
        """Limpar conexões mortas (rotina de manutenção)"""
        if not self.active_connections:
            return
        
        alive_connections = []
        for connection in self.active_connections:
            try:
                # Tentar enviar um ping simples
                await connection.ping()
                alive_connections.append(connection)
            except Exception:
                logger.info("Removing dead WebSocket connection")
        
        self.active_connections = alive_connections
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Obter estatísticas das conexões"""
        return {
            "active_connections": len(self.active_connections),
            "total_connections_created": self.connection_count,
            "has_active_connections": self.is_connected()
        }


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