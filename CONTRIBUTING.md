# Contribuindo

Obrigado por considerar contribuir!

## Como começar
1. Crie um fork do repositório
2. Crie um branch descritivo: `git checkout -b feat/nome-da-feature`
3. Execute os testes locais e o lintern
4. Envie um PR pequeno, objetivo e com descrição clara

## Padrões
- Python 3.10+
- Siga PEP8 (use `ruff` ou `flake8` se desejar)
- Mantenha logs claros e evite exceções silenciosas

## Commits
- Use mensagens no imperativo
- Exemplos: `fix(api): trata 403 do Cloudflare`, `feat(mm-grid): rebalance por limiar`

## Segurança
- Não inclua chaves, segredos ou `.env` em PRs
- Veja [SECURITY.md](SECURITY.md)