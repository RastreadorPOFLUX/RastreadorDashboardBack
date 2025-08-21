from datetime import datetime
from ipaddress import ip_address
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import time
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importações dos módulos locais
from models.schemas import *
from services.esp_communicator import ESPCommunicator
from services.websocket_manager import WSConnectionManager
from services.data_aggregator import DataAggregator

app = FastAPI(
    title="Rastreador Solar Dashboard API",
    description="API para comunicação com rastreador solar POF-LUX",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instâncias globais
esp_communicator = None
data_aggregator = None
ws_manager = WSConnectionManager()

# Cache para status de conexão
_last_check_time = 0
_last_check_status = False
CHECK_INTERVAL = 3  # segundos

# Dicionário para controlar se set_mode já foi chamado para cada cliente WebSocket
_client_mode_initialized = {}


@app.get("/")
async def root():
    return {"message": "Rastreador Solar Dashboard API", "status": "online"}


@app.post("/registerIP")
async def register_esp_device(data: DeviceRegistration, request: Request):
    global esp_communicator, data_aggregator

    try:
        parsed_ip = str(ip_address(data.ip))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"IP inválido: {data.ip}")

    logger.info(f"Requisição recebida de {request.client.host}")
    logger.info(f"Dados recebidos: device_id={data.device_id}, ip={parsed_ip}")

    # Se não existe, cria e o próprio ESPCommunicator cuida do WebSocket
    if esp_communicator is None:
        esp_communicator = ESPCommunicator(esp_ip=parsed_ip, device_id=data.device_id)
        data_aggregator = DataAggregator(esp_communicator)
        asyncio.create_task(data_aggregator.start_data_collection())
        logger.info("ESPCommunicator criado e DataAggregator iniciado.")
    else:
        # Atualiza configuração, o próprio ESPCommunicator reinicia o WS
        if not await esp_communicator.update_esp_config(parsed_ip, device_id=data.device_id):
            raise HTTPException(status_code=400, detail="Falha ao atualizar conexão com o ESP.")

    return {
        "status": "success",
        "message": f"ESP registrado/atualizado com IP {parsed_ip}",
        "connection_info": {"base_url": esp_communicator.base_url, "ws_url": esp_communicator.ws_url}
    }


@app.get("/api/health")
async def health_check():
    try:
        if esp_communicator is None:
            return {
                "api_status": "online",
                "esp_status": False,
                "esp_registered": False,
                "data_aggregator_status": False,
                "timestamp": int(time.time()),
                "system_health": {"status": "not_initialized", "message": "ESP não registrado"}
            }
        esp_status = await esp_communicator.check_connection()
        return {
            "api_status": "online",
            "esp_status": esp_status,
            "esp_registered": True,
            "data_aggregator_status": data_aggregator is not None,
            "timestamp": int(time.time()),
            "system_health": {"status": "ok" if esp_status else "error", "message": "OK" if esp_status else "Erro de conexão"},
            "connection_details": await esp_communicator.get_connection_status()
        }
    except Exception as e:
        logger.error(f"Erro ao verificar saúde do sistema: {str(e)}")
        return {"api_status": "error", "esp_status": False, "error": str(e)}


@app.get("/api/angles", response_model=AnglesResponse)
async def get_angles():
    if data_aggregator is None or esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    try:
        esp_data = await esp_communicator.get_angles_from_esp()
        return AnglesResponse(
            sun_position=float(esp_data.get("sunAngle", 0.0)),
            lens_angle=float(esp_data.get("lensAngle", esp_data.get("mpu", {}).get("lensAngle", 0.0))),
            manual_setpoint=float(esp_data.get("manualSetpoint", 0.0))
        )
    except Exception as e:
        logger.error(f"Erro ao obter ângulos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pid", response_model=PIDAdjustResponse)
async def get_pid_data():
    if data_aggregator is None or esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    try:
        esp_data = await esp_communicator.get_pid_from_esp()
        return PIDAdjustResponse(
            kp=float(esp_data.get("kp", 0.0)),
            ki=float(esp_data.get("ki", 0.0)),
            kd=float(esp_data.get("kd", 0.0))
        )
    except Exception as e:
        logger.error(f"Erro ao obter PID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/motor", response_model=MotorResponse)
async def get_motor_data():
    if data_aggregator is None or esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    try:
        data = await esp_communicator.get_motor_power_from_esp()
        motor_value = data.get("pwm", 0)
        return MotorResponse(
            power=round((motor_value / 255) * 100, 1),
            raw_value=int(motor_value)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system-status", response_model=SystemStatusResponse)
async def get_system_status():
    if data_aggregator is None or esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    try:
        data = await data_aggregator.get_current_data()
        return SystemStatusResponse(
            mode=data.get("mode", "unknown"),
            esp_clock=data.get("esp_clock", 0),
            rtc_day=data.get("rtc_day", 1),
            rtc_month=data.get("rtc_month", 1),
            rtc_year=data.get("rtc_year", 2024),
            rtc_hour=data.get("rtc_hour", 0),
            rtc_minute=data.get("rtc_minute", 0),
            rtc_second=data.get("rtc_second", 0),
            is_online=await esp_communicator.check_connection()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/mode")
async def set_operation_mode(mode_request: ModeRequest):
    if esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    success = await esp_communicator.set_mode(mode_request.mode, mode_request.manual_setpoint)
    if success:
        return {"status": "success", "mode": mode_request.mode, "manual_setpoint": mode_request.manual_setpoint}
    else:
        raise HTTPException(status_code=500, detail="Falha ao alterar modo.")


@app.patch("/api/adjustPid")
async def adjust_pid(pid_request: PIDResponse):
    if esp_communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")
    kp, ki, kd = pid_request.adjust.kp, pid_request.adjust.ki, pid_request.adjust.kd
    if not (0 <= kp <= 10 and 0 <= ki <= 10 and 0 <= kd <= 10):
        raise HTTPException(status_code=400, detail="Valores PID fora dos limites.")
    success = await esp_communicator.set_pid_parameters(kp, ki, kd)
    if success:
        return {"status": "success", "message": "Parâmetros PID ajustados."}
    else:
        raise HTTPException(status_code=500, detail="Falha ao ajustar PID.")


# WebSocket
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    global _last_check_time, _last_check_status
    
    # Gerar ID único para este cliente
    client_id = id(websocket)
    await ws_manager.connect(websocket)

    try:
        # Chamar set_mode apenas uma vez para este cliente
        if client_id not in _client_mode_initialized:
            if esp_communicator is not None:
                try:
                    # Obter o modo atual do sistema para sincronizar
                    system_data = await data_aggregator.get_current_data()
                    current_mode = system_data.get("mode", "auto")
                    current_setpoint = system_data.get("manual_setpoint", 0.0)
                    
                    # Sincronizar o modo do ESP com o dashboard
                    success = await esp_communicator.set_mode(current_mode, current_setpoint)
                    if success:
                        logger.info(f"Modo sincronizado para cliente {client_id}: {current_mode}, setpoint: {current_setpoint}")
                    else:
                        logger.warning(f"Falha ao sincronizar modo para cliente {client_id}")
                except Exception as e:
                    logger.error(f"Erro ao sincronizar modo para cliente {client_id}: {str(e)}")
            
            # Marcar como inicializado para este cliente
            _client_mode_initialized[client_id] = True

        while True:
            if data_aggregator is None or esp_communicator is None:
                await ws_manager.send_personal_json_message(
                    {"system_status": {"is_online": False, "message": "ESP não registrado"}},
                    websocket
                )
                await asyncio.sleep(1)
                continue

            # Cache de conexão
            now = time.time()
            if now - _last_check_time > CHECK_INTERVAL:
                try:
                    _last_check_status = await esp_communicator.check_connection()
                except Exception as e:
                    logger.error(f"Erro check_connection: {e}")
                    _last_check_status = False
                _last_check_time = now

            current_data = await data_aggregator.get_current_data()
            ws_data =  {
                "angles": {
                    "sunPosition": current_data.get("sun_position", 0),
                    "lensAngle": current_data.get("mpu", {}).get("lens_angle", 0),
                    "manualSetpoint": current_data.get("manual_setpoint", 0)
                },
                "motor": {
                    "power": round((current_data.get("motor", 0)/ 255) * 100, 1),
                    "raw_value": current_data.get("motor", 0)
                },
                "pid": {
                    "kp": current_data.get("pid_values", {}).get("kp", 0),
                    "ki": current_data.get("pid_values", {}).get("ki", 0),
                    "kd": current_data.get("pid_values", {}).get("kd", 0),
                    "p": current_data.get("pid_values", {}).get("p", 0),
                    "i": current_data.get("pid_values", {}).get("i", 0),
                    "d": current_data.get("pid_values", {}).get("d", 0),
                    "error": current_data.get("pid_values", {}).get("error", 0),
                    "output": current_data.get("pid_values", {}).get("output", 0)
                },
                "system_status": {
                    "mode": current_data.get("mode", "unknown"),
                    "esp_clock": current_data.get("esp_clock", 0),
                    "rtc_day": current_data.get("rtc_day", 1),
                    "rtc_month": current_data.get("rtc_month", 1),
                    "rtc_year": current_data.get("rtc_year", 2024),
                    "rtc_hour": current_data.get("rtc_hour", 0),
                    "rtc_minute": current_data.get("rtc_minute", 0),
                    "rtc_second": current_data.get("rtc_second", 0),
                    "is_online": await esp_communicator.check_connection()
                },
                "timestamp": current_data.get("processed_timestamp", data_aggregator.get_current_timestamp())
            }

            await ws_manager.send_personal_json_message(ws_data, websocket)
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        # Remover cliente do dicionário de controle ao desconectar
        if client_id in _client_mode_initialized:
            del _client_mode_initialized[client_id]
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Remover cliente do dicionário de controle em caso de erro
        if client_id in _client_mode_initialized:
            del _client_mode_initialized[client_id]
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
