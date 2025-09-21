# Guia rápido: Publicar no GitHub (passo a passo)

> Você só precisa fazer isso uma vez por projeto.

## 1) Criar repositório no GitHub
1. Acesse https://github.com e faça login
2. Clique em **New** (novo repositório)
3. Nome: `pacifica-grid-bot` (ou o nome que preferir)
4. **Desmarque** a opção de criar README automático (vamos usar o nosso)
5. Clique em **Create repository**

## 2) Configurar Git localmente
Instale o Git e configure seu usuário (uma vez só):
```bash
git config --global user.name "Seu Nome"
git config --global user.email "seu@email.com"
```

## 3) Iniciar o repositório local
No diretório do projeto:
```bash
git init
git add .
git commit -m "chore: primeiro commit do Pacifica Grid Bot"
```

## 4) Conectar o remoto e enviar
Copie a URL exibida pelo GitHub após criar o repositório (HTTPS ou SSH) e rode:
```bash
git remote add origin URL_DO_SEU_REPO
git branch -M main
git push -u origin main
```

## 5) Releases (opcional)
- Crie uma *tag* e *release* para versões estáveis:
```bash
git tag -a v0.1.0 -m "primeiro release"
git push origin v0.1.0
```

## 6) Proteções importantes
- Verifique se `.env` está no `.gitignore`
- Ative *Branch protection rules* para `main` (Settings → Branches)
- Ative *Dependabot alerts* (Settings → Code security and analysis)

## 7) Abrir o projeto
- Edite a descrição, tópicos (e.g. `crypto`, `trading-bot`, `grid`)
- Adicione um README com badges se quiser (CI, licença, etc.)
- Use Issues e Projects para tarefas

Pronto! Seu projeto está no ar.