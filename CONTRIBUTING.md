# Contribuir com o laboratório

Uma contribuição útil torna uma decisão mais clara para quem está aprendendo.

1. Descreva o problema ou caso de uso em uma issue, sem material interno.
2. Use um cenário fictício no formato de [incidents.example.json](incidents.example.json).
3. Indique qual categoria, referência de evidência ou erro de entrada você espera.
4. Faça uma alteração pequena e adicione um teste que observe esse comportamento.
5. Execute os comandos abaixo antes de abrir um pull request.

```text
python -m compileall -q agent.py test_agent.py
python -m unittest -v
python agent.py --mode demo --input incidents.example.json --incident INC-001
```

Em Linux/macOS, substitua `python` por `python3` quando necessário. Os testes não precisam de Ollama, chave, conta cloud ou dependências adicionais.

Exemplo: se a latência fictícia cair para 320 ms e a meta continuar em 400 ms, a avaliação não deve afirmar que essa métrica excede a meta. Um teste deve comparar a categoria obtida e conferir que nenhuma evidência inexistente foi incluída.

Mantenha arquivos pessoais em `local/`, que é ignorada pelo Git. Não inclua credenciais, logs, dados pessoais, capturas de sistemas internos ou configurações reais. A validação de formato não identifica automaticamente todo dado sensível.

Explique na descrição do pull request o problema, a mudança de comportamento e os testes executados. Não anuncie implantação Azure ou execução com modelo real quando a validação foi apenas local ou simulada.
