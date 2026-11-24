# Aprender com incidentes públicos

Este material seleciona e reformula fatos de dois postmortems publicados pelos próprios provedores. O objetivo é praticar leitura de evidências, separar impacto de causa e reconhecer os limites de uma ferramenta de triagem.

As entradas em [incidents.public.example.json](../incidents.public.example.json) são **resumos de análises posteriores**. Elas não reproduzem a telemetria completa, o conhecimento disponível durante a resposta ou uma experiência operacional de Tiago Silveira Siqueira. Os fatos e as análises pertencem às fontes identificadas abaixo.

Todas as evidências desse arquivo usam `observation`. Nenhum valor de CPU, memória, latência, taxa de erro ou limite operacional foi criado para preencher o esquema. Horários e durações citados são relatos das fontes, e não medições executadas por este projeto.

## Cloudflare — 2 de julho de 2019

**Fonte:** [Details of the Cloudflare outage on July 2, 2019](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/), John Graham-Cumming, publicado em 12/07/2019.

O artigo descreve uma atualização de regra do WAF cuja expressão regular causou backtracking excessivo e esgotamento de CPU dos processos HTTP/HTTPS. Clientes receberam erros 502 e a funcionalidade de proxy, CDN e WAF foi afetada.

O texto declara que seus horários são UTC. A implantação começou às 13:42; o WAF foi desativado globalmente às 14:07; às 14:09, tráfego e CPU estavam nos níveis esperados. A restauração da funcionalidade WAF foi uma etapa posterior. Portanto, a marca de 14:09 não significa que todas as etapas de recuperação terminaram nesse instante.

| Evidência do arquivo | Fato selecionado | Onde verificar na fonte |
|---|---|---|
| `E-401` | Implantação da alteração às 13:42 UTC | “What happened” |
| `E-402` | Relação entre regra, backtracking e esgotamento de CPU | “The events of July 2” |
| `E-403` | Erros HTTP 502 observados pelos clientes | “The events of July 2” |
| `E-404` | Desativação global do WAF às 14:07 UTC | “What happened” |
| `E-405` | Normalização de tráfego/CPU às 14:09 UTC; recuperação do WAF tratada depois | “What happened” |
| `E-406` | Limitações nos testes de consumo de CPU e no rollout daquela mudança | “What went wrong” |

Perguntas para aprendizagem:

- Que teste teria observado o modo de falha descrito, além de conferir se a regra funciona?
- Qual decisão de implantação ampliou o alcance da mudança?
- Como distinguir recuperação do tráfego de restauração de todas as funcionalidades?

Essas perguntas servem para análise e documentação. Não incluem a expressão regular original nem um procedimento para reproduzir a falha ou alterar um ambiente.

## GitHub — 21 e 22 de outubro de 2018

**Fonte:** [October 21 post-incident analysis](https://github.blog/news-insights/company-news/oct21-post-incident-analysis/), Jason Warner, publicado em 30/10/2018.

O artigo relata **24 horas e 11 minutos de degradação de serviço**. Ele informa que partes da plataforma não foram afetadas; portanto, esse período não deve ser apresentado como indisponibilidade total do GitHub.

Às 22:52 UTC de 21/10/2018, uma manutenção de equipamento óptico ocasionou perda de conectividade. A conectividade foi restabelecida em 43 segundos, mas o failover e as escritas divergentes entre locais desencadearam uma recuperação prolongada. A equipe priorizou integridade dos dados e pausou entrega de webhooks e builds de Pages. Às 23:03 UTC de 22/10/2018, o status foi atualizado para verde após o processamento pendente e a confirmação operacional descritos no artigo.

| Evidência do arquivo | Fato selecionado | Onde verificar na fonte |
|---|---|---|
| `E-501` | Manutenção e perda de conectividade às 22:52 UTC | “Background” |
| `E-502` | Restabelecimento em 43 segundos e degradação relatada de 24h11 | “Background” e abertura do artigo |
| `E-503` | Promoção de primários em outra região e escritas divergentes | “Incident timeline”, 21/10 às 22:52 UTC |
| `E-504` | Priorização da integridade e pausa de webhooks/Pages | “Incident timeline”, 21/10 às 23:19 UTC |
| `E-505` | Processamento pendente e status verde | “Incident timeline”, 22/10 às 23:03 UTC |

Perguntas para aprendizagem:

- Por que recuperar a conectividade não foi suficiente para encerrar o incidente?
- Que expectativas da aplicação precisavam estar alinhadas ao failover?
- Como comunicar a diferença entre serviço parcialmente degradado e indisponibilidade total?

O resumo descreve decisões históricas. Ele não apresenta SQL, credenciais, topologias executáveis ou comandos de resposta a incidentes.

## Executar o arquivo de estudo

Na raiz do repositório:

```text
python agent.py --mode demo --input incidents.public.example.json --list
python agent.py --mode demo --input incidents.public.example.json --incident INC-101
python agent.py --mode demo --input incidents.public.example.json --incident INC-102
```

Em Linux/macOS, substitua `python` por `python3` quando necessário.

Para os dois casos, a categoria do modo demo é `indeterminado`. Isso é esperado: as regras atuais precisam de métricas estruturadas e metas para categorias específicas. Descrever CPU em uma observação não equivale a fornecer um `cpu_percent`, e não autoriza inventar um número.

O resultado não significa que o postmortem desconhece a causa. Significa que este classificador por regras não transforma narrativa em telemetria. Ele mantém as referências às observações e permite reconhecer que o resumo causal está na fonte e exige leitura humana.

O modelo local opcional pode ajudar a resumir a narrativa, mas a validação continua exigindo suporte para a categoria escolhida. O programa não executa decisões mencionadas nos relatos.

Para reutilizar, copie o arquivo para `local/`, preserve a origem dos fatos no seu material de estudo e marque qualquer acréscimo inventado como simulação separada. Não misture uma hipótese didática com uma conclusão atribuída ao provedor.
