# 📋 Plano de Implementação — Notebook Price Monitor

> **Documento técnico de execução** para construção de ferramenta de monitoramento
> de preços de notebooks específicos em lojas dos EUA, com alertas via Telegram.

---

## 🎯 Para o Agente Executor (Sonnet)

Este plano é destinado a **outro agente IA (Claude Sonnet)** que executará a implementação
diretamente no workspace git. Leia este documento INTEIRO antes de começar.

**Premissas importantes:**

1. O ambiente de produção é um servidor Linux já existente, hospedando n8n em `n8n.bygianotto.com.br`
2. A ferramenta NÃO será integrada como nodes n8n — é uma aplicação Python standalone que **roda no mesmo servidor**
3. Alertas serão enviados via Telegram através de webhook do n8n (não diretamente da app Python)
4. Persistência é arquivo JSON local — sem banco de dados
5. Execução é via cron, 2x por dia

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Servidor (mesmo do n8n)                                    │
│                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │  cron (2x/dia)   │───▶│  monitor.py                  │  │
│  │  06:00 / 18:00   │    │  (entrypoint principal)      │  │
│  └──────────────────┘    └────────────┬─────────────────┘  │
│                                       │                     │
│                          ┌────────────┼────────────┐       │
│                          ▼            ▼            ▼       │
│                    ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│                    │ scrapers/│ │ storage/ │ │  alerts/ │ │
│                    │  *.py    │ │ json log │ │ webhook  │ │
│                    └──────────┘ └──────────┘ └────┬─────┘ │
│                                                    │       │
└────────────────────────────────────────────────────┼───────┘
                                                     │
                                                     ▼
                                         ┌──────────────────────┐
                                         │  n8n webhook         │
                                         │  ↓                   │
                                         │  Telegram bot        │
                                         └──────────────────────┘
```

### Princípios arquiteturais

1. **Simplicidade > sofisticação** — JSON file ao invés de SQLite/Postgres
2. **Fail-safe** — falha em uma loja não interrompe as demais
3. **Idempotência** — rodar 2x seguidas não causa duplicação
4. **Stateless scrapers** — cada scraper é uma função pura `(sku, config) -> Result`
5. **Logs estruturados** — JSON line format pra fácil debugging
6. **Sem state global** — config carregada uma vez por execução
7. **Dockerized** - The application will be dockerized and run as a container on the same server as n8n


---

## 📁 Estrutura de Diretórios

```
notebook-price-monitor/
├── README.md                      # Documentação do projeto
├── requirements.txt               # Dependências Python
├── config.example.yaml            # Template de configuração
├── config.yaml                    # Config real (gitignored)
├── .env.example                   # Template de variáveis de ambiente
├── .env                           # Vars reais (gitignored)
├── .gitignore
├── monitor.py                     # Entrypoint principal
├── src/
│   ├── __init__.py
│   ├── config.py                  # Carrega config.yaml + .env
│   ├── models.py                  # Dataclasses (Product, PriceCheck, etc.)
│   ├── storage.py                 # Read/write do JSON log
│   ├── alerts.py                  # Envio para webhook n8n
│   ├── orchestrator.py            # Loop principal de execução
│   └── scrapers/
│       ├── __init__.py
│       ├── base.py                # Classe base abstrata
│       ├── bestbuy.py             # Scraper Best Buy
│       ├── amazon.py              # Scraper Amazon
│       ├── newegg.py              # Scraper Newegg
│       ├── asus_shop.py           # Scraper ASUS Shop US
│       └── ebay.py                # Scraper eBay
├── data/
│   ├── price_log.json             # Log histórico (gitignored)
│   └── last_run.json              # Estado da última execução
├── logs/
│   └── monitor.log                # Log de execução (gitignored)
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_scrapers/
│   │   ├── test_bestbuy.py
│   │   ├── test_amazon.py
│   │   └── ...
│   └── fixtures/                  # HTML samples para teste
│       ├── bestbuy_sample.html
│       └── ...
├── scripts/
│   ├── install.sh                 # Setup inicial
│   ├── install_cron.sh            # Configura crontab
│   └── view_log.py                # CLI para visualizar histórico
└── docs/
    ├── ARCHITECTURE.md
    ├── ADDING_NEW_STORE.md        # Como adicionar nova loja
    └── ADDING_NEW_PRODUCT.md      # Como adicionar novo produto
```

---

## 🐍 Stack Técnica

### Dependências obrigatórias

```txt
# requirements.txt
requests>=2.31.0          # HTTP client
beautifulsoup4>=4.12.0    # HTML parsing
lxml>=5.0.0               # Parser rápido para BS4
pyyaml>=6.0               # Config files
python-dotenv>=1.0.0      # .env management
tenacity>=8.2.0           # Retry logic
loguru>=0.7.0             # Logging estruturado
fake-useragent>=1.4.0     # Rotação de user agents
```

### Dependências de dev

```txt
# requirements-dev.txt
pytest>=7.4.0
pytest-mock>=3.12.0
responses>=0.24.0         # Mock HTTP responses
black>=24.0.0
ruff>=0.1.0
mypy>=1.8.0
```

### Versão Python

- **Python 3.11+** (use features modernas: type hints, match/case, exception groups)
- Use type hints em TODAS as funções públicas

---

## 📦 Especificação dos Componentes

### 1. `monitor.py` — Entrypoint principal

```python
#!/usr/bin/env python3
"""
Notebook Price Monitor — Entrypoint
Uso: python monitor.py [--config config.yaml] [--dry-run]
"""
```

**Responsabilidades:**
- Parse de argumentos CLI (argparse)
- Carregar config + .env
- Inicializar logging (loguru)
- Chamar `orchestrator.run_all_checks()`
- Sair com código apropriado (0 = sucesso, 1 = erro parcial, 2 = erro fatal)

**Flags CLI obrigatórias:**
- `--config PATH` — caminho do config.yaml (default: `./config.yaml`)
- `--dry-run` — executa sem enviar alertas nem gravar log
- `--verbose` — log nível DEBUG
- `--store NAME` — roda apenas uma loja específica (para debug)
- `--product SKU` — roda apenas um produto específico

---

### 2. `src/models.py` — Dataclasses

Definir as seguintes dataclasses usando `dataclasses` ou `pydantic`:

```python
@dataclass
class Product:
    """Produto monitorado"""
    sku: str                    # Identificador único (ex: "UX3405CA-PS99T")
    name: str                   # Nome amigável
    target_price: float         # Preço-alvo para alerta
    must_have_terms: list[str]  # Termos que DEVEM estar na descrição (ex: ["120Hz", "3K"])
    blocklist_terms: list[str]  # Termos que NÃO podem aparecer (ex: ["FHD+", "60Hz"])
    stores: dict[str, str]      # {nome_loja: url_busca}

@dataclass
class PriceCheck:
    """Resultado de uma checagem individual"""
    product_sku: str
    store: str
    timestamp: str              # ISO 8601 UTC
    success: bool
    price: float | None         # USD
    url: str | None             # URL onde foi encontrado
    in_stock: bool
    raw_title: str | None       # Título original encontrado
    matched_terms: list[str]    # Termos que bateram
    error: str | None           # Mensagem de erro se success=False

@dataclass
class AlertEvent:
    """Evento que dispara alerta"""
    product_sku: str
    product_name: str
    store: str
    price: float
    target_price: float
    url: str
    timestamp: str
    reason: str                 # "price_drop" | "below_target" | "back_in_stock"
```

---

### 3. `src/config.py` — Configuração

Carrega de `config.yaml` (produtos, lojas, scraper config) e `.env` (secrets).

**Estrutura do `config.yaml`:**

```yaml
# Configurações gerais
general:
  user_agents_rotation: true
  request_timeout_seconds: 30
  max_retries: 3
  retry_backoff_seconds: 5
  parallel_requests: false      # Sequencial por padrão (mais seguro)

# Configurações por loja
stores:
  bestbuy:
    enabled: true
    rate_limit_seconds: 3       # Delay mínimo entre requests
    use_api: false              # Best Buy tem API, mas requer key

  amazon:
    enabled: true
    rate_limit_seconds: 5
    use_scraperapi: false       # Toggle para usar ScraperAPI se disponível

  newegg:
    enabled: true
    rate_limit_seconds: 3

  asus_shop:
    enabled: true
    rate_limit_seconds: 3

  ebay:
    enabled: true
    rate_limit_seconds: 3
    use_api: false

# Produtos monitorados
products:
  - sku: "UX3405CA-PS99T"
    name: "ASUS Zenbook 14 OLED PS99T (Ultra 9 285H, 32GB, 1TB, 3K 120Hz)"
    target_price: 1099.00
    must_have_terms:
      - "120Hz"
      - "32GB"
      - "285H"
    blocklist_terms:
      - "FHD+"
      - "60Hz"
      - "WUXGA"
      - "Refurbished"
      - "Renewed"
    stores:
      bestbuy: "https://www.bestbuy.com/site/searchpage.jsp?st=UX3405CA-PS99T"
      amazon: "https://www.amazon.com/s?k=UX3405CA-PS99T"
      newegg: "https://www.newegg.com/p/pl?d=UX3405CA-PS99T"
      asus_shop: "https://shop.asus.com/us/search?q=UX3405CA-PS99T"
      ebay: "https://www.ebay.com/sch/i.html?_nkw=UX3405CA-PS99T&_sop=15"

  - sku: "UX3405CA-ES99T"
    name: "ASUS Zenbook 14 OLED ES99T (Ultra 9 285H, 32GB, 1TB, 3K 120Hz, Win Home)"
    target_price: 1199.00
    must_have_terms:
      - "120Hz"
      - "32GB"
      - "285H"
    blocklist_terms:
      - "FHD+"
      - "60Hz"
      - "WUXGA"
    stores:
      bestbuy: "https://www.bestbuy.com/site/searchpage.jsp?st=UX3405CA-ES99T"
      amazon: "https://www.amazon.com/s?k=UX3405CA-ES99T"
      asus_shop: "https://shop.asus.com/us/90nb14w4-m022f0-asus-zenbook-14-ux3405.html"

  - sku: "UX3405CA-PZ194W"
    name: "ASUS Zenbook 14 OLED PZ194W (Ultra 7 255H, 16GB, 1TB, 3K 120Hz)"
    target_price: 899.00
    must_have_terms:
      - "120Hz"
      - "255H"
    blocklist_terms:
      - "FHD+"
      - "60Hz"
      - "WUXGA"
    stores:
      amazon: "https://www.amazon.com/s?k=UX3405CA-PZ194W"
      newegg: "https://www.newegg.com/p/pl?d=UX3405CA-PZ194W"
      ebay: "https://www.ebay.com/sch/i.html?_nkw=UX3405CA-PZ194W"

  # Adicionar outros produtos do TOP 5 conforme necessário

# Configuração de alertas
alerts:
  webhook_url: "${N8N_WEBHOOK_URL}"  # Lido do .env
  triggers:
    price_drop_percent: 5            # Alerta se cair 5%+ entre 2 checks
    below_target: true               # Alerta sempre que abaixo do target
    back_in_stock: true              # Alerta quando volta a ter estoque
  cooldown_minutes: 360              # Não repetir mesmo alerta em 6h
```

**Estrutura do `.env`:**

```bash
# .env
N8N_WEBHOOK_URL=https://n8n.bygianotto.com.br/webhook/notebook-price-alert
LOG_LEVEL=INFO
DATA_DIR=./data
LOG_DIR=./logs

# Opcional - se decidir usar ScraperAPI
SCRAPERAPI_KEY=

# Opcional - se decidir usar APIs oficiais
BESTBUY_API_KEY=
EBAY_API_KEY=
```

---

### 4. `src/storage.py` — Persistência JSON

**Responsabilidades:**
- Ler/escrever `data/price_log.json`
- Ler/escrever `data/last_run.json`
- Gerenciar arquivo atomicamente (write to .tmp + rename)
- Rotacionar log se passar de 10MB (criar `price_log.YYYY-MM-DD.json` e zerar)

**Estrutura do `price_log.json`:**

```json
{
  "version": "1.0",
  "created_at": "2026-05-27T18:00:00Z",
  "last_updated": "2026-05-27T18:00:30Z",
  "products": {
    "UX3405CA-PS99T": {
      "name": "ASUS Zenbook 14 OLED PS99T...",
      "target_price": 1099.00,
      "checks": [
        {
          "timestamp": "2026-05-27T06:00:15Z",
          "store": "bestbuy",
          "success": true,
          "price": 1299.00,
          "url": "https://www.bestbuy.com/...",
          "in_stock": true,
          "raw_title": "ASUS - Zenbook 14 14\" OLED Touch Laptop...",
          "matched_terms": ["120Hz", "32GB", "285H"]
        },
        {
          "timestamp": "2026-05-27T06:00:18Z",
          "store": "amazon",
          "success": false,
          "error": "Timeout after 30s"
        }
      ],
      "alerts_sent": [
        {
          "timestamp": "2026-05-27T06:00:30Z",
          "reason": "below_target",
          "price": 1049.00
        }
      ]
    }
  }
}
```

**Estrutura do `last_run.json`:**

```json
{
  "started_at": "2026-05-27T06:00:00Z",
  "completed_at": "2026-05-27T06:00:45Z",
  "duration_seconds": 45,
  "products_checked": 5,
  "stores_checked": 5,
  "successful_checks": 18,
  "failed_checks": 7,
  "alerts_sent": 1
}
```

**Funções esperadas:**

```python
def load_log() -> dict: ...
def save_log(data: dict) -> None: ...
def append_check(check: PriceCheck) -> None: ...
def get_last_check(sku: str, store: str) -> PriceCheck | None: ...
def get_alerts_sent(sku: str, hours: int = 6) -> list[AlertEvent]: ...
def append_alert(alert: AlertEvent) -> None: ...
def update_last_run(stats: dict) -> None: ...
def rotate_if_needed(max_mb: int = 10) -> None: ...
```

---

### 5. `src/scrapers/base.py` — Classe base

```python
from abc import ABC, abstractmethod

class BaseScraper(ABC):
    """Classe base para todos os scrapers"""
    
    name: str  # Nome da loja
    
    def __init__(self, config: dict, rate_limiter: RateLimiter):
        self.config = config
        self.rate_limiter = rate_limiter
    
    @abstractmethod
    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """
        Executa busca e retorna lista de resultados (pode haver múltiplos matches).
        Cada resultado vira um PriceCheck. Filtros (must_have/blocklist) são aplicados aqui.
        """
        ...
    
    def filter_results(self, results: list[dict], product: Product) -> list[dict]:
        """Aplica must_have_terms e blocklist_terms no título"""
        ...
```

---

### 6. Scrapers individuais

**ATENÇÃO ao agente executor:** Os seletores CSS/XPath de cada loja MUDAM com frequência.
Implemente com **resiliência**:

- Use try/except generosamente
- Fallback para múltiplos seletores (`#price`, `.price`, `[data-price]`)
- Log o HTML quando falhar (em arquivo separado por loja, max 1MB)
- Cada scraper deve retornar lista vazia em caso de falha total, NÃO erro fatal

#### `src/scrapers/bestbuy.py`

**Estratégia:**
- Tentar Best Buy Products API primeiro (se key disponível em `.env`)
- Fallback para scraping HTML da página de busca
- Selectors críticos: `.sku-title a`, `.priceView-customer-price > span`
- Best Buy bloqueia bots; usar headers realistas + delay entre requests
- Detectar "Sold Out" via texto ou ausência de botão "Add to Cart"

#### `src/scrapers/amazon.py`

**Estratégia:**
- Scraping puro (sem API oficial para products)
- Selectors críticos: `[data-component-type="s-search-result"]`, `.a-price .a-offscreen`
- Amazon tem proteção forte; rotação de User-Agent OBRIGATÓRIA
- Se response status 503 ou contém "Sorry, we just need to make sure", marcar como failed
- Considerar opção de usar ScraperAPI (se key em `.env`, usar como proxy)
- Extrair ASIN do URL para usar como identificador único

#### `src/scrapers/newegg.py`

**Estratégia:**
- Scraping HTML direto, Newegg é menos agressivo que Amazon
- Selectors: `.item-cell`, `.price-current strong`
- Atenção a item-cells de "Sponsored" — filtrar fora

#### `src/scrapers/asus_shop.py`

**Estratégia:**
- shop.asus.com tem busca interna; URL típica `?search-key=UX3405CA-PS99T`
- Selectors: `.ProductItem`, `.ProductItem__price`
- Geralmente disponível, mas estoque pode estar "Out of Stock" — detectar

#### `src/scrapers/ebay.py`

**Estratégia:**
- eBay tem Browse API oficial gratuita (recomendado se possível)
- Se sem API key, scraping de `https://www.ebay.com/sch/i.html?_nkw=...`
- Filtrar apenas "Buy It Now" (não leilão): adicionar `&LH_BIN=1` na URL
- Selectors: `.s-item`, `.s-item__price`
- IMPORTANTE: filtrar vendedores não-top-rated; checar `.s-item__seller-info-text`

---

### 7. `src/alerts.py` — Webhook do n8n

**Função única:**

```python
def send_alert(event: AlertEvent, webhook_url: str) -> bool:
    """
    Envia evento de alerta para webhook do n8n.
    n8n processa e dispara mensagem Telegram.
    
    Retorna True se POST teve status 2xx.
    """
```

**Payload esperado pelo webhook:**

```json
{
  "event_type": "price_alert",
  "timestamp": "2026-06-15T14:30:00Z",
  "product": {
    "sku": "UX3405CA-PS99T",
    "name": "ASUS Zenbook 14 OLED PS99T..."
  },
  "alert": {
    "reason": "below_target",
    "current_price": 1049.00,
    "target_price": 1099.00,
    "previous_price": 1299.00,
    "discount_from_target_percent": 4.5,
    "currency": "USD"
  },
  "store": {
    "name": "bestbuy",
    "url": "https://www.bestbuy.com/site/...",
    "in_stock": true
  },
  "message": "🔥 PREÇO ABAIXO DO TARGET!\n\nASUS Zenbook 14 OLED PS99T...\nBest Buy: $1,049.00 (target $1,099.00)\nEm estoque: ✅\n\nhttps://www.bestbuy.com/site/..."
}
```

**Lógica de trigger (no `orchestrator.py`):**

1. Se preço atual ≤ `target_price` E não houve alerta de "below_target" nas últimas 6h → enviar
2. Se preço caiu ≥ 5% comparado ao último check válido → enviar "price_drop"
3. Se estava out_of_stock no último check e agora está in_stock → enviar "back_in_stock"

---

### 8. `src/orchestrator.py` — Loop principal

**Pseudocódigo:**

```python
def run_all_checks(config: Config) -> RunStats:
    start_time = utcnow()
    stats = RunStats()
    
    for product in config.products:
        for store_name, search_url in product.stores.items():
            if not config.stores[store_name].enabled:
                continue
            
            try:
                scraper = get_scraper(store_name)
                results = scraper.search(product, search_url)
                
                # Filtrar pelos must_have/blocklist terms
                filtered = scraper.filter_results(results, product)
                
                # Pegar o melhor (menor preço in_stock)
                best = pick_best_result(filtered)
                
                if best:
                    storage.append_check(best)
                    check_and_alert(best, product, config)
                    stats.successful_checks += 1
                else:
                    storage.append_check(PriceCheck(
                        success=False, 
                        error="No matching results"
                    ))
                    stats.failed_checks += 1
                
            except Exception as e:
                logger.exception(f"Failed: {product.sku} @ {store_name}")
                stats.failed_checks += 1
            
            # Rate limit entre checks
            time.sleep(config.stores[store_name].rate_limit_seconds)
    
    stats.completed_at = utcnow()
    storage.update_last_run(stats.to_dict())
    return stats


def check_and_alert(check: PriceCheck, product: Product, config: Config):
    """Decide se dispara alerta baseado em regras"""
    
    # Regra 1: below_target
    if check.price <= product.target_price:
        if not _alert_sent_recently(product.sku, "below_target", hours=6):
            alert = AlertEvent(reason="below_target", ...)
            alerts.send_alert(alert, config.alerts.webhook_url)
            storage.append_alert(alert)
    
    # Regra 2: price_drop
    last_check = storage.get_last_check(product.sku, check.store)
    if last_check and last_check.price:
        drop_pct = (last_check.price - check.price) / last_check.price * 100
        if drop_pct >= config.alerts.triggers.price_drop_percent:
            alert = AlertEvent(reason="price_drop", ...)
            alerts.send_alert(alert, config.alerts.webhook_url)
            storage.append_alert(alert)
    
    # Regra 3: back_in_stock
    # ... similar
```

---

## 🤖 Configuração no n8n (lado do servidor)

**Importante:** este plano cobre apenas a app Python. O agente NÃO precisa configurar o n8n,
apenas DOCUMENTAR como configurar.

Criar arquivo `docs/N8N_SETUP.md` com instruções:

### Workflow n8n necessário

1. **Trigger node:** Webhook (POST)
   - URL: `/webhook/notebook-price-alert`
   - Method: POST
   - Authentication: header `X-API-Key` (opcional, recomendado)

2. **Telegram node:**
   - Bot token: configurar em credentials
   - Chat ID: do usuário (descobrir via `@userinfobot`)
   - Message: usar field `{{$json.message}}` que já vem formatado

3. **Optional:** Adicionar node "If" para filtrar por `event_type` ou `severity`

---

## 🧪 Critérios de Aceitação

O agente Sonnet deve garantir que cada item abaixo está OK antes de declarar concluído:

### Funcionais

- [ ] `python monitor.py --dry-run` executa sem erros e mostra resumo das checagens que faria
- [ ] `python monitor.py` executa e grava `data/price_log.json` corretamente
- [ ] Falha em uma loja NÃO impede checagem das outras
- [ ] Filtro `must_have_terms` está case-insensitive
- [ ] Filtro `blocklist_terms` está case-insensitive
- [ ] Alerta `below_target` dispara quando preço ≤ target
- [ ] Cooldown de 6h impede spam de alertas
- [ ] Rate limit entre requests é respeitado
- [ ] Logs aparecem em `logs/monitor.log` com nível, timestamp, mensagem estruturada
- [ ] Rotação de log de preços funciona quando arquivo passa 10MB

### Estruturais

- [ ] Todos os módulos têm docstring no topo
- [ ] Todas as funções públicas têm type hints
- [ ] `mypy src/` passa sem erros
- [ ] `ruff check src/` passa sem erros
- [ ] `black --check src/` passa sem erros
- [ ] Tests em `tests/` cobrem ao menos:
  - Models (criação, validação)
  - Storage (read/write, atomic, rotation)
  - Cada scraper (com HTML fixtures reais)
  - Orchestrator (mockado)
- [ ] `pytest` passa todos os testes

### Documentação

- [ ] `README.md` completo com: install, config, run, troubleshooting
- [ ] `docs/ARCHITECTURE.md` explica decisões técnicas
- [ ] `docs/ADDING_NEW_STORE.md` mostra como adicionar uma 6ª loja
- [ ] `docs/ADDING_NEW_PRODUCT.md` mostra como adicionar produto monitorado
- [ ] `docs/N8N_SETUP.md` com instruções para o webhook
- [ ] `.env.example` documenta TODAS as vars
- [ ] `config.example.yaml` tem comentários explicando cada campo

### Deployment

- [ ] `scripts/install.sh` cria venv, instala deps, prepara estrutura
- [ ] `scripts/install_cron.sh` configura crontab (com confirmação interativa)
- [ ] Crontab default: `0 6,18 * * * cd /path/to/app && /path/to/venv/bin/python monitor.py`
- [ ] Healthcheck endpoint opcional (HTTP /healthz) — fora do escopo inicial

### Segurança

- [ ] `.env` e `config.yaml` reais estão no `.gitignore`
- [ ] Secrets NUNCA aparecem em logs (mascarar webhook URL parcialmente se logado)
- [ ] Webhook URL não é hardcoded em nenhum lugar
- [ ] User-Agent rotation está ativa por default

---

## 🎢 Plano de Implementação por Fases

### Fase 1: Foundation (1-2h de trabalho do agente)

1. Setup do projeto (estrutura de pastas, `requirements.txt`, `.gitignore`, `.env.example`)
2. `src/models.py` completo
3. `src/config.py` carregando YAML + .env
4. `src/storage.py` com testes
5. `src/alerts.py` com função `send_alert`
6. Commit: "feat: project foundation, models, storage, alerts"

### Fase 2: First Scraper (1-2h)

1. `src/scrapers/base.py`
2. `src/scrapers/bestbuy.py` (mais fácil, menos anti-bot)
3. Testes do scraper com fixtures HTML
4. `src/orchestrator.py` v1 (só Best Buy)
5. `monitor.py` entrypoint com `--dry-run`
6. Validar manualmente: rodar `python monitor.py --dry-run --store bestbuy`
7. Commit: "feat: best buy scraper + orchestrator v1"

### Fase 3: Demais scrapers (2-3h)

1. `src/scrapers/asus_shop.py`
2. `src/scrapers/newegg.py`
3. `src/scrapers/ebay.py`
4. `src/scrapers/amazon.py` (último porque é o mais difícil)
5. Cada um com fixture HTML + teste
6. Validação manual loja por loja
7. Commits separados: "feat: <store> scraper" cada

### Fase 4: Lógica de alertas (1h)

1. Implementar 3 triggers (below_target, price_drop, back_in_stock)
2. Cooldown
3. Testes de unidade
4. Validar fluxo end-to-end com webhook fake (httpbin.org/post)
5. Commit: "feat: alert logic with cooldown"

### Fase 5: Deployment e Docs (1h)

1. `scripts/install.sh`
2. `scripts/install_cron.sh`
3. `scripts/view_log.py` (CLI bonitinho com tabela)
4. README.md completo
5. docs/ARCHITECTURE.md
6. docs/ADDING_NEW_STORE.md
7. docs/ADDING_NEW_PRODUCT.md
8. docs/N8N_SETUP.md
9. Commit: "docs: complete documentation + deploy scripts"

### Fase 6: Hardening (opcional, se sobrar tempo)

1. Healthcheck HTTP endpoint
2. Métricas (Prometheus format ou similar)
3. Validação de schema com pydantic
4. CI básico (GitHub Actions: lint + test)

---

## ⚠️ Armadilhas Conhecidas

O agente executor deve ANTECIPAR estas issues:

### Anti-bot Amazon

- Amazon retorna página de captcha se detectar bot
- Sinais: status 503, ou HTML contendo "Sorry, we just need to make sure"
- **Mitigação:** User-Agent realista + delay de 5s+ + considerar ScraperAPI
- **Fallback:** se Amazon falhar 3x consecutivas, criar alerta de "scraper_broken"

### Mudança de seletores

- Lojas mudam HTML mensalmente; expect breakage
- **Mitigação:** múltiplos seletores em fallback; log de HTML quando falha
- **Mitigação 2:** testes com fixtures detectam quebra cedo

### URL changes

- Best Buy especialmente muda URLs com frequência (slug + SKU no path)
- **Mitigação:** usar URL de busca interna ao invés de URL direta do produto

### Timezone

- Sempre usar UTC interno (`datetime.now(timezone.utc)`)
- Converter para timezone local APENAS na hora de exibir

### Race conditions no JSON

- Cron pode rodar 2x simultâneo se anterior demorou
- **Mitigação:** lock file (`/tmp/notebook_monitor.lock`)
- Se lock existe há mais de 1h, considera órfão e remove

### Rotação de log

- JSON cresce indefinidamente
- **Implementação:** ao iniciar, checar tamanho; se > 10MB, mover para `price_log.YYYY-MM-DD.json.gz` e começar novo

### Dependências do servidor

- O servidor do n8n provavelmente roda Docker
- Decidir: rodar Python diretamente no host OU containerizar
- **Recomendação:** rodar direto no host com venv Python (mais simples); containerizar é over-engineering para essa escala

---

## 🔐 Considerações de Segurança

1. **Webhook URL** é praticamente um secret — qualquer um com a URL pode mandar alertas falsos
   - Adicionar header `X-API-Key` no POST (verificado no n8n)
   - Validar n8n só aceita POSTs com User-Agent específico

2. **JSON log** pode conter URLs com tokens em alguns casos
   - Não logar URLs com query params sensíveis (raro, mas possível)

3. **.env** nunca deve aparecer em commits
   - `.gitignore` deve listar `.env`, `config.yaml`, `data/`, `logs/`

4. **Permissões de arquivo no servidor:**
   - `chmod 600 .env` (só dono lê)
   - `chmod 755 monitor.py`
   - Diretório `data/` com `chmod 750`

---

## 📊 Métricas de Sucesso

Após 1 semana rodando, considera-se sucesso se:

1. ✅ Cron executou 14x (2/dia × 7 dias) com 0 crashes fatais
2. ✅ Ao menos 4 das 5 lojas estão respondendo (Amazon pode falhar)
3. ✅ Pelo menos 1 alerta foi enviado e recebido no Telegram (mesmo que false-positive)
4. ✅ Log JSON tem entrada coerente por produto/loja a cada execução
5. ✅ Tamanho do JSON < 5MB após 1 semana

---

## 🚀 Comandos de Referência Rápida

```bash
# Setup inicial (uma vez)
git clone <repo> notebook-price-monitor
cd notebook-price-monitor
./scripts/install.sh

# Configurar
cp config.example.yaml config.yaml
cp .env.example .env
# Editar ambos com valores reais

# Testar manualmente
source venv/bin/activate
python monitor.py --dry-run

# Rodar uma vez de verdade
python monitor.py

# Ver histórico de preços bonitinho
python scripts/view_log.py

# Ver apenas um produto
python scripts/view_log.py --sku UX3405CA-PS99T

# Instalar cron
./scripts/install_cron.sh

# Debug uma loja específica
python monitor.py --store bestbuy --verbose

# Reset de logs (cuidado!)
rm data/price_log.json
echo '{"version":"1.0","products":{}}' > data/price_log.json
```

---

## 📝 Notas Finais para o Agente

1. **Não over-engineer.** A meta é uma ferramenta útil em 2 meses, não um produto SaaS.

2. **Teste localmente cada scraper** antes de seguir para o próximo. HTML real > especulação.

3. **Commits pequenos e frequentes.** Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).

4. **Quando em dúvida sobre uma decisão de design:**
   - Simplicidade > flexibilidade
   - Explícito > implícito
   - Funcionar > ser elegante

5. **Logs são seu melhor amigo.** Use `loguru` generosamente.

6. **Se quebrar:**
   - Tente fix rápido se a causa é óbvia
   - Se não é óbvio, escreva um teste que reproduz o bug ANTES de fixar
   - Documente em `docs/TROUBLESHOOTING.md` casos não-óbvios

7. **O usuário (Victor) é systems engineer:**
   - Pode aceitar configuração via YAML sem GUI
   - Vai rodar comandos de terminal
   - Vai debuggar se precisar
   - Prefere logs estruturados, não verbosos

8. **Janela de tempo do projeto:**
   - Implementação: agora até início de Junho 2026
   - Operação: 1º Junho até final de Julho 2026 (~2 meses)
   - Após compra do notebook: desligar cron, arquivar repo

---

*Documento preparado para handoff ao agente executor.*  
*Última revisão: 27 de Maio de 2026*
