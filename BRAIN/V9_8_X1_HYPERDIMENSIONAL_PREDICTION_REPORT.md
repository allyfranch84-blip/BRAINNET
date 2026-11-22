# V9.8-X1 — Predição hiperdimensional em simulação

**Recomendação:** não integrar este desenho à produção. No cenário sintético estudado, a superposição FHRR teve alto descarte do resultado correto para estados de origem não vistos e latência maior que as duas referências simples. O experimento não demonstra ganho geral nem invalida outras arquiteturas hiperdimensionais.

## Implementações e segurança

Foram inspecionados `hyperdimensional.py` (FHRR), `ghrr_core.py` (GHRR), `qfhrr_core.py` (QFHRR), `world_model.py`, `world_model_engine.py` e `htn_planner.py`. O Kernel instancia `WorldModelEngine`; o MLP `WorldModel` é distinto, e este ensaio não o treinou nem alegou integrá-lo. O experimento isolado `experiments/v98_x1_hdc_benchmark.py` reutiliza os três motores; não abre janelas, não executa ações físicas, não escreve em memória persistente da BRAINNET e não é chamado pelo Kernel.

## Método

Estado exato `(x, foco, botão)` possui 8 posições e dois bits; ações left/right saturam limites; toggle altera botão somente com foco e x=2 ou 5. As transições são regras determinísticas. Sementes 11, 29 e 47, com 24 estados origem de treino e 8 de teste por semente. Destinos do treino podem coincidir com estados reservados como origem de teste; não é teste de vocabulário ou domínio totalmente desconhecido.

FHRR: chave `k=s⊙a`, memória `M=phase(sum_i(k_i⊙s'_i))`, consulta `q=M⊙conj(k)`, similaridade `Re(vdot(q,c))/d`. Top-3 de estados resultantes é comparado à transição exata; somente o estado correto é aceito pelo verificador-oráculo simulado. Nas trajetórias de 1, 2, 4 e 8 passos, quando o correto não está no top-3, a tentativa é marcada sem sucesso. Esta verificação tem acesso à regra verdadeira: custo do oráculo não está incluído na latência FHRR e não existe como garantia gratuita em apps reais. A sequência de ações é fixa: esta implementação avalia candidatos de **estados**, não ranking top-k de ações ou um planejador completo.

Referências: regra exata e dicionário de transições treinadas. A regra é um limite superior porque conhece o ambiente; o dicionário retorna ausência para pares não treinados. Não há chamadas de LLM em nenhum caminho.

Ensaio independente de interferência codifica pares aleatórios chave/valor em uma superposição e recupera top-1. FHRR usa 512 dimensões complex64; QFHRR usa 512 componentes uint8, sparsity=1; GHRR usa dimensão 256, matrizes 2×2 complex64 e `unbind_left`, pois chave está à esquerda. Capacidade não é comparável diretamente sem equalizar representação e orçamento. Os testes de ruído acrescentam fase gaussiana σ=0,25 rad apenas às chaves FHRR. Não foi testada supressão por evidência além da filtragem exata por oráculo.

## Resultados

Média entre três sementes. Latências abaixo são medianas das estatísticas por semente, não p95 agregado; medidas em microsegundos com tracemalloc ativo. A latência FHRR inclui ranking de 32 estados; as referências não pagam esse custo.

| Horizonte | Top-1 FHRR correto | Recall top-3 | Eliminação indevida | Objetivo verificado | Cobertura da tabela |
|---|---:|---:|---:|---:|---:|
| 1 | 16,7% | 25,0% | 75,0% | 25,0% | 0,0% |
| 2 | 14,6% | 25,0% | 75,0% | 16,7% | 6,2% |
| 4 | 12,5% | 21,9% | 78,1% | 4,2% | 24,0% |
| 8 | 10,9% | 18,2% | 81,8% | 0,0% | 23,4% |

A referência exata retorna a regra por construção; 100% de previsão não é desempenho aprendido. A tabela é exata quando possui par, mas sua cobertura nos estados reservados inicialmente é 0. A soma de candidatos incorretos do top-3 ao longo de todos os horizontes foi 343, 353 e 310 por semente; são candidatos falsos antes do filtro exato, não ações executadas.

| Referência | p50 | p95 |
|---|---:|---:|
| Regra exata | 4,10 µs | 5,10 µs |
| Dicionário | 4,20 µs | 5,13 µs |
| FHRR + top-3 | 359,55 µs | 415,66 µs |

Inicialização FHRR e construção da memória por semente: 7,11–7,91 ms, sem incluir importação de bibliotecas nem aquecimento Numba. `NUMBA_DISABLE_JIT=1` foi usado para reproduzir CPU sem compilação; os tempos não representam ambiente de produção. FHRR em arrays persistentes do ensaio de transições: 147.456 bytes; tabela possui 72 entradas, memória total não medida.

Recall top-1 na recuperação associativa de pares aleatórios:

| Pares | FHRR 512D | QFHRR 512D | GHRR 256D |
|---|---:|---:|---:|
| 4 | 100% | 100% | 100% |
| 16 | 100% | 100% | 100% |
| 64 | 83,3% | 34,9% | 83,3% |

Com σ=0,25 rad, FHRR teve 100%, 100% e 82,3%, respectivamente. Esses pontos indicam degradação entre 16 e 64 neste cenário; **capacidade máxima não foi determinada**. Para 64 pares, bytes dos arrays persistentes (memória + chaves + valores) foram FHRR 528.384, QFHRR 66.048 e GHRR 528.384, sem overhead Python ou temporários. A simulação de pesos 3:1 produziu similaridades 0,970 e 0,204; fase oposta teve −1,000, sem implicar ação errada.

## Recursos, validação e limites

Python 3.12.10, NumPy 2.5.4; duração total medida 3,47 s. Pico de alocações via tracemalloc 4.826.714 bytes; RSS antes/depois 38.219.776 / 42.946.560 bytes, não pico de RSS nem memória exclusiva do modelo. VRAM não medida; CPU somente. Inferências LLM evitadas: não medidas, pois as referências não usam LLM; não há evidência de redução.

`python -m unittest test_v98x1_experiment -v`: 3 aprovados. `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas, JUnit `development_logs/REGRESSION_20261112_201649_278559.xml`. Dados completos, por semente: `development_logs/V9_8_X1_RESULTS.json`.

Reprodução PowerShell em `A:\BRAINNET\BRAIN`:

```
$env:PYTHONPATH=(Get-Location).Path
$env:NUMBA_DISABLE_JIT='1'
python experiments\v98_x1_hdc_benchmark.py
```

O ensaio é pequeno, com 3 sementes, horizonte curto, x discreto e verificador perfeito; não mede utilidade em aplicativos, aprendizado causal real, top-k de ações ou comparação de custo ponta a ponta. Melhor investigação exigiria representar atributos composicionalmente para generalizar e comparar modelos treinados com igual informação e custos de verificação incluídos. Até demonstrar confiabilidade e ganho em tarefas representativas, manter fora da rota de produção.
