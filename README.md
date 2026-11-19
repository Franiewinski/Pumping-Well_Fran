# NVO — Bombeamento (implantação online)

Aplicação Streamlit para análise exploratória de testes de produção em poço único.

## Publicação sem instalar nada no computador

1. Acesse https://github.com/new e crie um repositório, preferencialmente **privado** para o código.
2. Abra o repositório, use **Add file > Upload files**, e envie **app.py** e **requirements.txt** (arquivos extraídos deste ZIP, não o ZIP).
3. Acesse https://share.streamlit.io/ e entre com o GitHub.
4. Clique **Create app**, selecione o repositório, branch `main` e arquivo principal `app.py`.
5. Publique; a plataforma fornecerá uma URL `*.streamlit.app`.

Tudo ocorre no navegador. O computador da empresa não precisa executar `pip` nem `streamlit`.

## Dados e segurança

Não envie dados de processos internos sem autorização institucional e uma avaliação de privacidade, segurança e regras de retenção da hospedagem. Repositório privado não garante, por si só, que o app ou os dados enviados sejam privados.

## Planilha de entrada

Colunas obrigatórias: `tempo_min`, `nivel_m` (nível medido em profundidade a partir do mesmo referencial do NE). Opcional: `vazao_m3h`.

## Limitações

Protótipo não homologado. Recuperação e teste escalonado ainda não executam interpretação completa. A biblioteca `pumptest` é instalada a partir do GitHub no ambiente remoto. A compatibilidade em deploy deve ser testada.
