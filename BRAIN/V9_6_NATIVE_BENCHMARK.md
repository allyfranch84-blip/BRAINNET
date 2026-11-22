# V9.6 — extensão nativa e benchmark

Nenhum benchmark Rust versus NumPy foi executado: cargo, rustc e maturin não foram encontrados no PATH/ambiente Python consultado. Não foi criada nem compilada extensão nativa; não se conclui ganho, paridade ou compatibilidade. Não houve download, instalação ou compilação. A execução sem Rust não foi validada por inicialização integral do Kernel nesta missão; os testes de regressão simulados passaram sem extensão.

Polars e LanceDB não estão instalados no Python consultado; provas de conceito e benchmarks comparativos permanecem pendentes. Reusar benchmarks e perfis já registrados em V9.4 antes de selecionar operação nativa; medir correção, p50/p95 e memória em workloads representativos, com fallback existente, antes de alterar o Kernel.
