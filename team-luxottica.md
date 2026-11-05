# Tech Race - credenziali del team team-luxottica

**Traccia**: architecture-refactoring

Queste sono le credenziali del solo team **team-luxottica**: consegnale a quel team e a nessun altro. Tra parentesi trovi il segnaposto del brief che ogni valore sostituisce.

## OpenShift

| Cosa                            | Valore                                                                                                                      |
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| Console web (<CONSOLE_URL>)     | https://console-openshift-console.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com                                         |
| Cluster API (<CLUSTER_API_URL>) | https://api.itz-50mouq.infra01-lb.lon04.techzone.ibm.com:6443                                                               |
| Username                        | team-luxottica                                                                                                              |
| Password                        | techrace                                                                                                                    |
| Namespace                       | team-luxottica-ns                                                                                                           |
| Registry immagini               | default-route-openshift-image-registry.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com/team-luxottica-ns/<immagine>:<tag> |

## Gitea (stesse credenziali di OpenShift)

| Cosa              | Valore                                                                                                                                                     |
|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| Gitea             | https://gitea-gitea-system.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com                                                                               |
| Il tuo repository | https://gitea-gitea-system.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com/team-luxottica/architecture-refactoring.git                                   |
| Clone             | git clone https://team-luxottica:techrace@gitea-gitea-system.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com/team-luxottica/architecture-refactoring.git |

## Mailpit (posta di test del tuo team)

| Cosa                               | Valore                                                                                 |
|----------------------------------|--------------------------------------------------------------------------------------|
| Interfaccia web                    | https://mailpit-ui-team-luxottica-ns.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com |
| Username                           | team-luxottica                                                                         |
| Password                           | techrace                                                                               |
| Server SMTP (SMTPS, TLS implicito) | mailpit-smtp-team-luxottica-ns.apps.itz-50mouq.infra01-lb.lon04.techzone.ibm.com       |
| Porta SMTP                         | 443                                                                                    |

Gli stessi dati di Mailpit sono nel ConfigMap `team-info` del tuo namespace.