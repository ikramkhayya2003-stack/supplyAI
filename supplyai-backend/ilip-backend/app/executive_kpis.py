"""Eight traceable executive KPIs; all calculations reside in PostgreSQL."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from .db import get_connection
router=APIRouter(prefix='/dashboard',tags=['Executive KPI'])

@router.get('/executive-kpis')
def executive_kpis(start_date:date|None=None,end_date:date|None=None,conn=Depends(get_connection)):
    coverage=conn.execute('SELECT min(snapshot_date) AS first_date,max(snapshot_date) AS last_date FROM ilip.inventory_levels').fetchone()
    if not coverage['first_date'] or not coverage['last_date']:
        raise HTTPException(404,'Aucune période disponible dans les photographies de stock.')
    start=start_date or coverage['first_date'];end=end_date or coverage['last_date']
    if start>end or start<coverage['first_date'] or end>coverage['last_date'] or (end-start).days>366:
        raise HTTPException(422,'Période chronologique de 367 jours maximum dans les dates de stock disponibles.')
    summary=conn.execute('SELECT ilip.kpi_report(%s,%s) AS report',(start,end)).fetchone()['report']
    monthly=conn.execute("""SELECT m::date AS month, ilip.kpi_report(greatest(m::date,%s::date),
      least((m+interval '1 month - 1 day')::date,%s::date)) AS report
      FROM generate_series(date_trunc('month',%s::date),date_trunc('month',%s::date),'1 month') m ORDER BY m""",(start,end,start,end)).fetchall()
    return {'start_date':start,'end_date':end,'coverage':coverage,'summary':summary,
      'monthly':[dict(month=r['month'],**r['report']) for r in monthly],
      'definitions':{
        'otif_pct':'Lignes clients livrées intégralement à temps / lignes dues. Pondéré par nombre de lignes.',
        'oee_pct':'Somme(temps cycle idéal × bonnes pièces premier passage) / temps planifié. Agrégation pondérée en minutes.',
        'first_pass_yield_pct':'Bonnes pièces au premier passage / pièces totales. Retouches exclues du numérateur.',
        'cumulative_savings_eur':'Cumul net depuis le début de la période sélectionnée : volume × (coût référence − coût réel) − déploiement. Écritures approuvées avant fin de période seulement.',
        'scrap_rate_pct':'Pièces rebutées définitivement / pièces totales. Ne mesure pas les chutes de fil en mètres.',
        'machine_availability_pct':'Temps de marche / temps planifié sur les lots mesurés. Ne couvre pas tout le calendrier de la flotte.',
        'inventory_accuracy_pct':'Comptages physiques exactement égaux au stock système / comptages réalisés. Échantillon compté, tolérance zéro.',
        'lost_time_incidents':'Cas professionnels confirmés avec jours de travail perdus > 0, sur la période. Nombre de cas, pas LTIFR.'},
      'warnings':[
        'Les quatre KPI de production couvrent les enregistrements terminaux des OF achevés, attribués à leur date de fin réelle. Pas un indicateur temps réel par shift.',
        'Version V1 : une mesure terminale par OF, unité EA. OF sans enregistrement, mesures manquantes ou désaccord avec les sources : KPI production masqués.',
        'Disponibilité × performance × qualité pondérée en temps = OEE. Le FPY global en pièces peut différer de cette qualité pondérée avec plusieurs cycles idéaux.',
        'Sans attestation complète pour tous les sites/jours : économies et incidents indisponibles. Aucune mesure ou aucun dénominateur : indisponible.',
        'Les objectifs ne sont pas configurés : aucun badge on/off target inventé.',
        'Les états de commande, incidents et validations sont ceux actuellement enregistrés, filtrés par dates déclarées ; ce n’est pas un historique bitemporel.'
      ]}
