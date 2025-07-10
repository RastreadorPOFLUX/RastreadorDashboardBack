#!/usr/bin/env python3
"""
Script de teste para verificar funcionamento do backend
Rastreador Solar Dashboard
"""

import asyncio
import httpx
import json
import time
import websockets
from datetime import datetime

# Configurações
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/live"

async def test_http_endpoints():
    """Testar todos os endpoints HTTP"""
    print("🔍 Testando endpoints HTTP...")
    
    async with httpx.AsyncClient() as client:
        endpoints = [
            ("/", "GET", "Endpoint raiz"),
            ("/api/health", "GET", "Saúde do sistema"),
            ("/api/angles", "GET", "Dados de ângulos"),
            ("/api/motor", "GET", "Dados do motor"),
            ("/api/pid", "GET", "Dados PID"),
            ("/api/system-status", "GET", "Status do sistema"),
            ("/api/control-signals", "GET", "Sinais de controle"),
            ("/api/solar-irradiation", "GET", "Irradiação solar"),
            ("/api/statistics", "GET", "Estatísticas"),
            ("/api/demo-data", "GET", "Dados de demonstração"),
        ]
        
        results = []
        
        for endpoint, method, description in endpoints:
            try:
                response = await client.request(method, f"{BASE_URL}{endpoint}")
                status = "✅ OK" if response.status_code == 200 else f"❌ {response.status_code}"
                results.append((endpoint, status, description))
                print(f"  {endpoint:<25} | {status}")
                
                # Log dos dados para alguns endpoints importantes
                if endpoint in ["/api/demo-data", "/api/health"] and response.status_code == 200:
                    data = response.json()
                    print(f"    → {json.dumps(data, indent=2)[:100]}...")
                    
            except Exception as e:
                results.append((endpoint, f"❌ ERROR: {str(e)[:50]}", description))
                print(f"  {endpoint:<25} | ❌ ERROR: {e}")
        
        return results

async def test_control_endpoints():
    """Testar endpoints de controle"""
    print("\n🎮 Testando endpoints de controle...")
    
    async with httpx.AsyncClient() as client:
        # Testar mudança de modo
        modes = ["auto", "manual", "halt"]
        
        for mode in modes:
            try:
                response = await client.patch(
                    f"{BASE_URL}/api/mode",
                    json={"mode": mode}
                )
                
                if response.status_code == 200:
                    print(f"  ✅ Modo '{mode}' configurado com sucesso")
                else:
                    print(f"  ❌ Falha ao configurar modo '{mode}': {response.status_code}")
                    
                # Aguardar um pouco entre mudanças
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"  ❌ Erro ao testar modo '{mode}': {e}")
        
        # Testar ajuste RTC
        try:
            current_timestamp = int(time.time())
            response = await client.patch(
                f"{BASE_URL}/api/rtc",
                json={"timestamp": current_timestamp}
            )
            
            if response.status_code == 200:
                print(f"  ✅ RTC ajustado com sucesso: {current_timestamp}")
            else:
                print(f"  ❌ Falha ao ajustar RTC: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Erro ao testar ajuste RTC: {e}")

async def test_websocket():
    """Testar conexão WebSocket"""
    print("\n📡 Testando WebSocket...")
    
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("  ✅ WebSocket conectado com sucesso")
            
            # Aguardar algumas mensagens
            for i in range(3):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    print(f"  📨 Mensagem {i+1} recebida:")
                    print(f"    → Timestamp: {data.get('timestamp', 'N/A')}")
                    print(f"    → Ângulo solar: {data.get('angles', {}).get('sunPosition', 'N/A')}°")
                    print(f"    → Modo: {data.get('system_status', {}).get('mode', 'N/A')}")
                    
                except asyncio.TimeoutError:
                    print(f"  ⏰ Timeout aguardando mensagem {i+1}")
                    break
                except json.JSONDecodeError:
                    print(f"  ❌ Erro ao decodificar JSON da mensagem {i+1}")
                
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"  ❌ Erro na conexão WebSocket: {e}")

async def test_performance():
    """Testar performance básica"""
    print("\n⚡ Testando performance...")
    
    async with httpx.AsyncClient() as client:
        # Teste de múltiplas requisições simultâneas
        start_time = time.time()
        
        tasks = []
        for _ in range(10):
            task = client.get(f"{BASE_URL}/api/demo-data")
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        successful = sum(1 for r in responses if isinstance(r, httpx.Response) and r.status_code == 200)
        
        print(f"  📊 10 requisições simultâneas em {total_time:.2f}s")
        print(f"  ✅ {successful}/10 sucessos")
        print(f"  ⚡ Média: {total_time/10:.3f}s por requisição")

async def main():
    """Função principal de teste"""
    print("🚀 Iniciando testes do backend...")
    print(f"📍 URL Base: {BASE_URL}")
    print(f"🔌 WebSocket: {WS_URL}")
    print(f"🕐 Horário: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Verificar se o servidor está rodando
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")
            if response.status_code != 200:
                print("❌ Servidor não está respondendo corretamente")
                return
        
        # Executar todos os testes
        await test_http_endpoints()
        await test_control_endpoints()
        await test_websocket()
        await test_performance()
        
        print("\n" + "=" * 60)
        print("✅ Testes concluídos!")
        print("\n📋 Próximos passos:")
        print("  1. Verificar se ESP está conectado")
        print("  2. Testar frontend React")
        print("  3. Verificar dados em tempo real")
        
    except Exception as e:
        print(f"\n❌ Erro geral nos testes: {e}")
        print("\n🔧 Verificar se:")
        print("  - Backend está rodando: python app.py")
        print("  - Porta 8000 não está ocupada")
        print("  - Dependências instaladas: pip install -r requirements.txt")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Testes interrompidos pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro ao executar testes: {e}") 