# 💻 Projeto: Compra de Notebook para Migração Linux Definitiva

> Documento de decisão e plano de execução para aquisição de notebook ultraportátil
> para uso como ferramenta principal de trabalho (systems engineering, dev, infra).

---

## 📌 Contexto

Migração do PC desktop atual (i5-10400F + RTX 2060) para um notebook ultraportátil,
visando uso como ferramenta principal para:

- Programação e desenvolvimento (Docker, git, IDE, ambiente de teste pré-deploy)
- Gerenciamento remoto de infraestrutura via SSH
- Vibe coding com LLMs (servidas remotamente de outro PC)
- Uso em casa (com 2 monitores externos) e mobilidade
- Wine para jogos eventuais
- Edição de imagem/vídeo ocasional

**Sistema operacional definido:** Ubuntu Linux (definitivo, sem dual-boot Windows)

---

## 🎯 Keys (Requisitos Decisivos)

| # | Requisito | Justificativa |
|---|---|---|
| 1 | **Tela 14" OLED 120Hz** | Conforto visual em jornadas de 8h+, monitores externos já são IPS |
| 2 | **Linux Ubuntu nativo** | Paridade com servidores de produção (x86_64), workflow DevOps |
| 3 | **32GB RAM ideal** (16GB aceitável) | Docker + IDE + browser + VMs; RAM soldada não tem upgrade |
| 4 | **1TB SSD** | Armazenamento confortável para projetos + Docker images + VMs |
| 5 | **iGPU competente** (Arc 140T preferível) | Wine para jogos eventuais + edição leve |
| 6 | **Visual ASUS Zenbook (preferência pessoal)** | Estética importa em ferramenta de uso diário |

### Não-requisitos (resolvidos externamente)

- ❌ LLM local pesado → será servido via Ollama no PC com RTX 3060 12GB na LAN
- ❌ NPU robusto → vibe coding usa Claude/ChatGPT via API
- ❌ Tela touch obrigatória → bonus, não requisito
- ❌ Bateria 15h+ → uso majoritariamente conectado

---

## 🏆 TOP 5 Candidatos

| # | Marca | Modelo | Descrição | Configuração Base | Preço (US$) | Origem |
|---|---|---|---|---|---|---|
| 🥇 | ASUS | **Zenbook 14 OLED UX3405CA-PS99T** | Ultrabook premium 14" com OLED 3K 120Hz touch, Arrow Lake-H, all-metal, 1.2 kg | Ultra 9 285H + 32GB LPDDR5x + 1TB SSD + 3K (2880x1800) 120Hz OLED touch + Arc 140T + Win 11 Pro | **$1.299** | Best Buy (esgotado, monitorar) |
| 🥈 | ASUS | **Zenbook 14 OLED UX3405CA-ES99T** | Mesma máquina do PS99T, vendido oficialmente pela ASUS Shop US | Ultra 9 285H + 32GB + 1TB + 3K 120Hz OLED touch + Win 11 Home | **$1.399** | ASUS Shop US (em estoque) |
| 🥉 | ASUS | **Zenbook 14 OLED UX3405CA (Mytrix)** | Mesma config 3K 120Hz, mas via reseller Mytrix (caixa aberta para incluir acessório) | Ultra 9 285H + 32GB + 1TB + 3K 120Hz OLED touch + Win 11 Pro + acessório Mytrix | **~$1.300-1.450** | Amazon US (ASIN B0GHXT6M1Y) |
| 4️⃣ | ASUS | **Zenbook 14 OLED UX3405CA-PZ194W** | Versão 16GB com Ultra 7 255H e 3K 120Hz | Ultra 7 255H + 16GB + 1TB + 3K 120Hz OLED touch + Win 11 Home | **~$800-950** | Internacional (Newegg/eBay; raro no US) |
| 5️⃣ | ASUS | **Vivobook S16 S5606CA-MS96** | Alternativa 16" se desistir do formato 14"; mesmo chip e iGPU | Ultra 9 285H + 32GB + 1TB + 16" 2.8K 120Hz OLED (não-touch) + RGB backlit | **~$1.300-1.400** | Amazon US, Adorama (ICP Hub reseller) |

### Modelos descartados explicitamente

| Modelo | Motivo do descarte |
|---|---|
| MacBook Air M5 | Sem suporte Linux estável (Asahi não suporta M5); abandona migração Linux |
| Dell 14 Plus DB14250 | Tela 90Hz IPS não atende key de 120Hz; SSD M.2 2230 incompatível com SN770 existente |
| Lenovo Yoga 7i (Ultra 7 155U) | CPU classe U (low-power) insuficiente; tela 60Hz |
| ASUS Q425MA-U71TB (155H) | Tela OLED 60Hz não atende key de 120Hz |
| ASUS Zenbook Duo UX8406 | 2ª tela não funciona em Linux; já tem 2 monitores externos; +$500 sem benefício real |
| Listings "FHD+ 60Hz" (IST, Mytrix variantes) | Tela 60Hz viola requisito principal |
| Lenovo ThinkPad T14 Gen 5 | Visual não agrada ("cara de Lenovo") |

---

## 🔍 Como identificar a versão CERTA do Zenbook UX3405CA

⚠️ **Atenção crítica**: o mesmo "UX3405CA" tem duas variantes de tela com nomes confusos.

### A tela 120Hz que queremos (✅ CORRETO)

Procurar na descrição por:
- **"3K"** ou **"WQXGA+"** ou **"2880x1800"**
- **"120Hz"**
- SKUs típicos: `PS99T`, `ES99T`, `PZ194W`, `PZ438W`, `PZ462W`, `PZ163WS`, `OU73210BL0X`

### A tela 60Hz que NÃO queremos (❌ ERRADO)

Bandeiras vermelhas na descrição:
- **"FHD+"** ou **"WUXGA"** ou **"1920x1200"**
- **"60Hz"**
- SKUs típicos: `U7321TB`, `U9321TB` (Jasper Gray geralmente é 60Hz)

### Bandeiras vermelhas de reseller

- "IST Computer Customized" → SSD trocado, caixa aberta
- "Mytrix Accessory" → caixa aberta para incluir mouse/hub
- "Ivy Bridge" → similar
- "ICP Hub" → similar
- "w/ Lifetime Office" / "w/ Accessory" → quase sempre caixa aberta

**Implicação**: lacre rompido pode complicar garantia ASUS. Não invalida automaticamente, mas pode gerar atrito em RMA.

---

## 💰 Estratégia de Compra

### Cronograma

```
Maio (atual)  →  Junho  →  Julho (compra)  →  Julho (viagem + chegada)
```

### Logística confirmada

- **Onde comprar:** lojas US (Amazon, Best Buy, ASUS Shop, Newegg, B&H, eBay top sellers)
- **Endereço de entrega:** colega de trabalho residente nos EUA
- **Retirada:** pessoalmente em viagem em Julho
- **Importação:** bagagem de mão, cota isenção US$ 1.000/pessoa

### Datas-chave de promoção (US)

| Data | Evento | Desconto típico |
|---|---|---|
| ~15 Junho | Father's Day | 10-15% |
| 28 Junho - 7 Julho | **4th of July week** | **20-30%** ⭐ |
| Meados de Julho | **Amazon Prime Day** | **20-30%** ⭐ |

### Targets de preço (para pull-the-trigger)

| Faixa | Preço-alvo PS99T | Ação |
|---|---|---|
| 🎯 Excelente | < $1.099 | **Comprar imediato** |
| ✅ Bom | $1.100 - $1.199 | Comprar |
| ⚖️ Justo | $1.200 - $1.299 | Comprar se urgência |
| ⚠️ Alto | $1.300+ | Esperar mais |

### Cálculo de custo final (estimado)

| Cenário | Preço notebook | Imposto BR | Total estimado |
|---|---|---|---|
| Notebook US$ 1.099 (oferta 4th July) | US$ 1.099 | ~US$ 50 (excesso $99) | **~R$ 5.745** (a R$5/USD) |
| Notebook US$ 1.299 (Best Buy padrão) | US$ 1.299 | ~US$ 150 (excesso $299) | **~R$ 7.245** |
| Notebook US$ 1.399 (ASUS Shop) | US$ 1.399 | ~US$ 200 (excesso $399) | **~R$ 7.995** |

---

## 🌐 Plano de Monitoramento

### Ferramentas gratuitas recomendadas (setup: 15 min)

| Ferramenta | Função | Link |
|---|---|---|
| **CamelCamelCamel** | Histórico Amazon + alertas email | https://camelcamelcamel.com |
| **Keepa** | Extensão browser, gráficos preço Amazon | https://keepa.com |
| **Slickdeals** | Alertas de comunidade (Best Buy/Amazon/Newegg) | https://slickdeals.net |
| **Best Buy "Notify Me"** | Email quando produto volta ao estoque | https://www.bestbuy.com (no SKU 6616966) |
| **NowInStock** | Alerta restock genérico | https://www.nowinstock.net |
| **Honey** | Extensão browser, histórico de preço multi-loja | https://www.joinhoney.com |

### ASINs/SKUs para cadastrar

```
Amazon ASINs:
- B0GHXT6M1Y (Mytrix PS99T 3K 120Hz)
- B0FPWWP83J (Ultra 9 285H FHD+ 60Hz)
- B0G64CCGLW (Vivobook S16 285H 32GB)

Best Buy SKUs:
- 6616966 (PS99T - Foggy Silver, 3K 120Hz) ⭐ PRIMARY
- JJGGLH7H3Y (Ultra 9 285H FHD+ 60Hz - Jasper Gray) — só se aceitar 60Hz
```

### Lojas para monitoramento semanal

| Loja | URL de busca |
|---|---|
| Amazon US | `https://www.amazon.com/s?k=UX3405CA-PS99T` |
| Best Buy | `https://www.bestbuy.com/site/searchpage.jsp?st=Zenbook+14+OLED+UX3405CA` |
| ASUS Shop US | `https://shop.asus.com/us/` |
| Newegg | `https://www.newegg.com/p/pl?d=Zenbook+UX3405CA+285H` |
| B&H Photo | `https://www.bhphotovideo.com` |
| eBay (Swing Computers) | `https://www.ebay.com/sch/i.html?_nkw=UX3405CA-PS99T&_sop=15` |
| Adorama | `https://www.adorama.com` |

### Opção de automação própria (caso queira)

Se quiser monitoramento automatizado próprio (rodando 2x/dia em VPS),
**não cobrimos a implementação neste README**, mas foram identificadas 3 abordagens:

1. **Workflow n8n** no servidor existente (`n8n.victorgianotto.com.br`) — Cron + HTTP Request + Telegram alert
2. **Script Python** com ScraperAPI (tier free 1000 req/mês cobre o uso) + SQLite log
3. **Webapp Flask** com dashboard local

**Recomendação prática:** começar com CamelCamelCamel + Slickdeals (gratuitos, robustos)
e só implementar solução própria se houver tempo/interesse técnico além do necessário.

---

## ⚙️ Plano de Execução Pós-Compra

### Antes do colega receber

- [ ] Cartão de crédito internacional configurado (Visa/Mastercard com tax-free shopping)
- [ ] Endereço do colega validado com a loja (Amazon especialmente)
- [ ] Confirmar com colega data exata da viagem em Julho

### Recepção (colega faz)

- [ ] Tirar foto da caixa lacrada antes de abrir
- [ ] Conferir SKU exato no rótulo (deve ser PS99T ou variante 3K 120Hz)
- [ ] Abrir com cuidado, manter caixa
- [ ] Ligar Windows uma vez (ativa licença vinculada ao hardware)
- [ ] Atualizar BIOS via Windows Update / MyASUS
- [ ] **Testar tela**: dead pixels, 120Hz funcional (Settings → Display → Refresh Rate)
- [ ] Testar todas teclas (online keyboard tester)
- [ ] Testar portas USB-A, 2x Thunderbolt 4, HDMI
- [ ] Testar áudio (speakers e jack 3.5mm)
- [ ] Testar Wi-Fi 7 e Bluetooth
- [ ] Verificar bateria carrega e descarrega normalmente
- [ ] Criar pendrive Windows recovery (Settings → Recovery)
- [ ] Documentar serial number + tirar foto da nota fiscal
- [ ] Guardar fechado até a viagem

### Após chegada no Brasil

#### Setup inicial Linux

- [ ] Baixar Ubuntu 25.04 ISO (kernel 6.14+ é melhor para Arrow Lake-H)
- [ ] Criar pendrive bootável via Ventoy ou Rufus
- [ ] Desabilitar Secure Boot temporariamente no BIOS
- [ ] Instalar Ubuntu apagando Windows
- [ ] Criar partição `/home` separada (boa prática)
- [ ] `sudo apt update && sudo apt full-upgrade`

#### Fixes específicos do Zenbook + Arrow Lake-H

- [ ] Instalar kernel `linux-oem` se brilho OLED travar no máximo
- [ ] `powerprofilesctl set performance` se notar throttling
- [ ] Atualizar firmware via `fwupd`
- [ ] Configurar `tlp` ou `power-profiles-daemon` para gestão de bateria
- [ ] Validar suspend/resume (importante para Arrow Lake-H)

#### Setup vibe coding remoto

- [ ] No PC com RTX 3060 (Linux ou WSL2):
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5-coder:14b-instruct-q4_K_M
  
  sudo systemctl edit ollama.service
  # Adicionar:
  # [Service]
  # Environment="OLLAMA_HOST=0.0.0.0:11434"
  
  sudo systemctl restart ollama
  ```
- [ ] Configurar IP fixo no PC ou usar Tailscale
- [ ] Liberar porta 11434 só na LAN/Tailscale
- [ ] No notebook: instalar VSCode + extensão Continue.dev
- [ ] Configurar Continue.dev apontando para `http://IP-RTX3060:11434`

#### Migração de workflow

- [ ] Repositório git de dotfiles (`.bashrc`, `.config/nvim`, `.ssh/config`)
- [ ] SSH keys regeneradas e adicionadas aos servidores remotos
- [ ] Docker + Docker Compose instalados
- [ ] Ferramentas dev: `git`, `nvim`, `tmux`, `fzf`, `ripgrep`, `bat`, `eza`
- [ ] Browsers configurados (Firefox/Chrome com sync)
- [ ] Configurar 2 monitores externos via Thunderbolt 4
- [ ] Testar carga do ambiente: Docker + IDE + browser + LLM remoto simultâneos

---

## 📊 Tabelas de Referência Técnica

### Comparativo de CPUs Intel relevantes

| Chip | Arquitetura | Cores | iGPU | NPU | Geekbench Multi | Linux Maturity |
|---|---|---|---|---|---|---|
| Ultra 7 155H | Meteor Lake | 16 (6P+8E+2LPE) | Arc (Xe) | 11 TOPS | ~12.500 | ⭐⭐⭐⭐⭐ |
| Ultra 7 255H | Arrow Lake-H | 16 (6P+8E+2LPE) | **Arc 140T** | 13 TOPS | ~14.500 | ⭐⭐⭐ |
| Ultra 9 285H | Arrow Lake-H | 16 (6P+8E+2LPE) | **Arc 140T** | 13 TOPS | ~16.000 | ⭐⭐⭐ |
| Ultra 7 258V | Lunar Lake | 8 (4P+4E) | Arc 140V | 47 TOPS | ~10.500 | ⭐⭐⭐⭐ |

### Performance LLM local (servidor com RTX 3060 12GB)

| Modelo | VRAM | Tokens/s | Uso recomendado |
|---|---|---|---|
| `qwen2.5-coder:7b-instruct-q8_0` | ~7.5GB | ~55 | Coding, autocomplete |
| `qwen2.5-coder:14b-instruct-q4_K_M` | ~8GB | ~30 | **Vibe coding principal** ⭐ |
| `deepseek-coder-v2:16b-lite-instruct-q4_K_M` | ~10GB | ~25 | Code review, refactoring |
| `llama3.1:8b-instruct-q5_K_M` | ~6GB | ~50 | Generalista |
| `nomic-embed-text` | ~300MB | n/a | Embeddings (RAG/codebase indexing) |

---

## 🔄 Status do Projeto

- ✅ Pesquisa de mercado concluída
- ✅ Requisitos definidos
- ✅ TOP 5 candidatos identificados
- ✅ Logística de importação definida
- ✅ Cronograma estabelecido (compra em Julho 2026)
- ⏳ Monitoramento de preços em andamento
- ⏳ Setup do servidor LLM (Ollama + RTX 3060) — pendente
- ⏳ Preparação de dotfiles e scripts de provisionamento — pendente
- ⏳ Compra — Julho 2026
- ⏳ Chegada e setup Linux — Julho/Agosto 2026

---

## 📝 Notas Finais

### Sobre maturidade Linux do Arrow Lake-H

Padrão histórico Intel-Linux: hardware novo demanda ~6 meses para maturar drivers
no kernel mainline. Arrow Lake-H foi lançado Jan/2025; em Maio/2026 está em fase
final de polimento. Até Julho/2026 (mais 2 meses), espera-se:

- Suspend S0iX totalmente funcional (patches em kernel 6.16+)
- Driver de iGPU Arc 140T estável (já está em 6.14)
- Brilho OLED Zenbook resolvido sem `linux-oem` kernel especial

### Sobre o WD_BLACK SN770 1TB existente

SSD M.2 2280 PCIe Gen 4 single-sided — **compatível com o slot do Zenbook 14**.

Como o modelo escolhido (PS99T) já vem com 1TB de fábrica (Samsung PM9C1),
o SN770 pode ser:

1. Usado como SSD externo (case USB-C Sabrent/Orico, ~US$ 30)
2. Mantido como peça de reposição (caso o original falhe)
3. Vendido (~R$ 250-350)

### Sobre garantia ASUS no Brasil

ASUS oferece **International Warranty** de 1 ano, mas com exclusão explícita para
**América do Sul e América Latina**. Implicação prática:

- Em caso de defeito, o aparelho precisa voltar aos EUA
- Custo de logística pode inviabilizar RMA pequenos
- Comprar em loja com ADP (Accidental Damage Protection) ajuda muito

**Lojas que dão ADP grátis (1 ano) via programa ASUS 90-Day Warranty Extension:**
- ✅ Amazon US, Newegg, ASUS Shop
- ❌ Best Buy (excluído do programa)

---

## 📚 Referências e Links Úteis

- ASUS Zenbook 14 OLED (UX3405) — Página oficial: https://www.asus.com/us/laptops/for-home/zenbook/asus-zenbook-14-ux3405/
- Best Buy PS99T — SKU 6616966: https://www.bestbuy.com/product/asus-zenbook-14-14-oled-touch-laptop-intel-core-ultra-9-285h-with-32gb-memory-intel-arc-graphics-1tb-storage-foggy-silver/JJGGLQV6QY
- ASUS 90-Day Warranty Extension: https://www.asus.com/us/site/90-day-warranty-reviews/
- Ollama: https://ollama.com
- Continue.dev: https://continue.dev
- Ubuntu Downloads: https://ubuntu.com/download/desktop

---

*Última atualização: 27 de Maio de 2026*
*Compra prevista: Julho de 2026*
