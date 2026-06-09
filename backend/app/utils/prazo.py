from datetime import datetime, timedelta

PRAZOS_DIAS = {
    'rescisao':     1,
    'certidao':     1,
    'notas_fiscais': 3,
}

_HORA_INICIO = 8
_HORA_FIM = 18


def calcular_prazo(tipo: str, criado_em: datetime) -> datetime:
    """
    Retorna o prazo limite em dias úteis (seg-sex, 08:00-18:00).
    Se criado fora do horário comercial, o contador começa às 08:00 do próximo dia útil.
    """
    n_dias = PRAZOS_DIAS.get(tipo, 1)
    inicio = criado_em.replace(second=0, microsecond=0)
    hora = inicio.hour + inicio.minute / 60

    # Ajustar para o próximo início de dia útil se fora do horário
    if inicio.weekday() >= 5 or hora < _HORA_INICIO or hora >= _HORA_FIM:
        if hora >= _HORA_FIM:
            inicio += timedelta(days=1)
        inicio = inicio.replace(hour=_HORA_INICIO, minute=0)
        while inicio.weekday() >= 5:
            inicio += timedelta(days=1)

    # Adicionar N dias úteis
    prazo = inicio
    adicionados = 0
    while adicionados < n_dias:
        prazo += timedelta(days=1)
        if prazo.weekday() < 5:
            adicionados += 1

    return prazo
