# Guia de Integração: Modos de Operação Frontend React ↔ Backend FastAPI

## 🎯 Objetivo

Este guia mostra como integrar os **modos de operação** (auto, manual, halt, presentation) entre o frontend React TypeScript (`RastreadorDashboardFront`) e o backend FastAPI (`RastreadorDashboardBack`), mantendo toda a estilização original.

## 📋 Pré-requisitos

- Backend FastAPI rodando em `http://localhost:8000`
- Frontend React TypeScript já configurado
- Axios instalado no frontend (`npm install axios`)

## 🔧 Estrutura da Integração

### Backend - Endpoints Disponíveis

O backend já possui os endpoints necessários:

```http
# Obter modo atual
GET http://localhost:8000/api/system-status

# Alterar modo de operação  
PATCH http://localhost:8000/api/mode
Content-Type: application/json
{
  "mode": "auto" | "manual" | "halt" | "presentation"
}

# Verificar saúde da API
GET http://localhost:8000/api/health
```

### Frontend - Arquivos a Criar

Para integrar os modos de operação, você precisará criar **3 arquivos** no frontend:

```
src/
├── types/
│   └── api.ts                    # Tipos TypeScript
├── services/
│   └── operationModeApi.ts       # Serviços de API
└── hooks/
    └── useOperationMode.ts       # Hook customizado
```

## 📝 Passo a Passo da Integração

### Passo 1: Criar Tipos TypeScript

Crie o arquivo `src/types/api.ts`:

```typescript
// Tipos para os modos de operação
export type OperationMode = 'auto' | 'manual' | 'halt' | 'presentation';

// Interface para requisição de mudança de modo
export interface ModeRequest {
  mode: OperationMode;
}

// Interface para resposta do status do sistema
export interface SystemStatusResponse {
  mode: OperationMode;
  esp_clock: number;
  rtc_day: number;
  rtc_month: number;
  rtc_year: number;
  rtc_hour: number;
  rtc_minute: number;
  rtc_second: number;
  is_online: boolean;
}

// Interface para resposta padrão da API
export interface ApiResponse<T> {
  data: T;
  status: number;
}
```

### Passo 2: Criar Serviço de API

Crie o arquivo `src/services/operationModeApi.ts`:

```typescript
import axios from 'axios';
import { OperationMode, ModeRequest, SystemStatusResponse } from '../types/api';

// Configuração base da API
const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Serviços específicos para modos de operação
export const operationModeApi = {
  // Obter modo atual do sistema
  getCurrentMode: async (): Promise<OperationMode> => {
    const response = await api.get<SystemStatusResponse>('/api/system-status');
    return response.data.mode;
  },

  // Alterar modo de operação
  setMode: async (mode: OperationMode): Promise<void> => {
    const request: ModeRequest = { mode };
    await api.patch('/api/mode', request);
  },

  // Verificar se API está online
  checkHealth: async (): Promise<boolean> => {
    try {
      await api.get('/api/health');
      return true;
    } catch {
      return false;
    }
  },
};
```

### Passo 3: Criar Hook Customizado

Crie o arquivo `src/hooks/useOperationMode.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { OperationMode, operationModeApi } from '../services/operationModeApi';

interface UseOperationModeReturn {
  currentMode: OperationMode;
  isLoading: boolean;
  isOnline: boolean;
  error: string | null;
  setMode: (mode: OperationMode) => Promise<void>;
}

export const useOperationMode = (): UseOperationModeReturn => {
  const [currentMode, setCurrentMode] = useState<OperationMode>('auto');
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Função para obter modo atual
  const fetchCurrentMode = useCallback(async () => {
    try {
      const mode = await operationModeApi.getCurrentMode();
      setCurrentMode(mode);
      setIsOnline(true);
      setError(null);
    } catch (err) {
      setIsOnline(false);
      setError('Erro ao conectar com o backend');
      console.error('Erro ao buscar modo atual:', err);
    }
  }, []);

  // Função para alterar modo
  const setMode = useCallback(async (mode: OperationMode) => {
    setIsLoading(true);
    setError(null);
    
    try {
      await operationModeApi.setMode(mode);
      setCurrentMode(mode);
      setIsOnline(true);
    } catch (err) {
      setError('Erro ao alterar modo de operação');
      console.error('Erro ao alterar modo:', err);
      // Recarregar modo atual em caso de erro
      await fetchCurrentMode();
    } finally {
      setIsLoading(false);
    }
  }, [fetchCurrentMode]);

  // Verificar conectividade inicial
  useEffect(() => {
    const checkConnection = async () => {
      const online = await operationModeApi.checkHealth();
      setIsOnline(online);
      
      if (online) {
        await fetchCurrentMode();
      }
    };

    checkConnection();
  }, [fetchCurrentMode]);

  // Polling a cada 5 segundos para sincronizar com backend
  useEffect(() => {
    const interval = setInterval(fetchCurrentMode, 5000);
    return () => clearInterval(interval);
  }, [fetchCurrentMode]);

  return {
    currentMode,
    isLoading,
    isOnline,
    error,
    setMode,
  };
};
```

### Passo 4: Integrar no Componente Existente

No componente `OperationModeCard`, substitua a lógica existente pelo hook:

```typescript
// No início do componente, importe o hook
import { useOperationMode } from '../../hooks/useOperationMode';

// Dentro do componente, substitua o estado local
const { currentMode, isLoading, isOnline, error, setMode } = useOperationMode();

// Use as funções nos botões:
// - currentMode: modo atual
// - setMode(modo): função para alterar modo
// - isLoading: estado de carregamento
// - isOnline: status de conexão
// - error: mensagem de erro (se houver)
```

## 🔍 Como Utilizar

### Verificar Modo Atual
```typescript
console.log('Modo atual:', currentMode); // 'auto', 'manual', 'halt', ou 'presentation'
```

### Alterar Modo
```typescript
await setMode('manual'); // Muda para modo manual
await setMode('auto');   // Muda para modo automático
```

### Verificar Status
```typescript
if (isOnline) {
  console.log('Backend conectado');
} else {
  console.log('Backend desconectado');
}

if (error) {
  console.log('Erro:', error);
}
```

## 🚀 Testando a Integração

### 1. Iniciar Backend
```bash
cd RastreadorDashboardBack
python app.py
```

### 2. Iniciar Frontend
```bash
cd RastreadorDashboardFront
npm run dev
```

### 3. Testes Manuais

1. **Teste de conexão**: Verifique se o indicador de status mostra "conectado"
2. **Teste de modos**: Clique nos botões de modo e veja se o modo atual muda
3. **Teste de sincronização**: Altere o modo via API e veja se o frontend atualiza
4. **Teste de erro**: Pare o backend e veja se o frontend mostra erro

### 4. Teste via Curl
```bash
# Verificar modo atual
curl http://localhost:8000/api/system-status

# Alterar para modo manual
curl -X PATCH http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "manual"}'
```

## ⚡ Características da Integração

- **Tempo Real**: Sincronização automática a cada 5 segundos
- **Feedback Visual**: Estados de loading e erro
- **Reconexão**: Tentativa automática de reconexão
- **TypeScript**: Tipagem completa para segurança
- **Error Handling**: Tratamento robusto de erros
- **Estado Consistente**: Sincronização entre frontend e backend

## 🔧 Troubleshooting

### Backend não responde
```bash
# Verificar se backend está rodando
curl http://localhost:8000/api/health
```

### CORS Error
Verificar se CORS está configurado no backend para `http://localhost:5173`

### Timeout
Aumentar timeout no arquivo `operationModeApi.ts` se necessário

### Estado inconsistente
O polling automático irá sincronizar o estado a cada 5 segundos

## ✅ Checklist de Integração

- [ ] Arquivos TypeScript criados (`types/api.ts`, `services/operationModeApi.ts`, `hooks/useOperationMode.ts`)
- [ ] Hook integrado no componente `OperationModeCard`
- [ ] Backend rodando na porta 8000
- [ ] Frontend conectando com sucesso
- [ ] Botões de modo funcionando
- [ ] Status de conexão exibido
- [ ] Sincronização automática funcionando

---

*Este guia foca especificamente na integração dos modos de operação, mantendo toda a estilização e estrutura existente do frontend.* 