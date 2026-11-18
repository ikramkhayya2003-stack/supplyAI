export const number = value => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value);
export const ratio = (a,b) => number(a) == null || number(b) == null || number(b)<=0 ? null : number(a)*100/number(b);
export const supplierRate = row => number(row.due_supplier_lines)==null || number(row.late_supplier_lines)==null ? null : ratio(number(row.due_supplier_lines)-number(row.late_supplier_lines),row.due_supplier_lines);
export const stockValue = row => !row.stock_date || number(row.missing_cost_items)==null || number(row.missing_cost_items)>0 ? null : number(row.stock_value_eur);
export const fmt = (value, decimals=0) => number(value)==null ? '—' : new Intl.NumberFormat('fr-FR',{maximumFractionDigits:decimals}).format(number(value));
export const pct = value => number(value)==null ? 'Non applicable' : `${fmt(value,2)} %`;
export function validateOverview(d){
 if(!d || !d.summary || !Array.isArray(d.monthly) || !/^\d{4}-\d{2}-\d{2}$/.test(d.start_date||'') || !/^\d{4}-\d{2}-\d{2}$/.test(d.end_date||'') || !d.coverage?.first_date || !d.coverage?.last_date) throw Error('Réponse du tableau de bord invalide. Vérifiez /dashboard/overview.');
 return d;
}
export function metrics(d){const k=d.executive.summary,e=k.evidence;const v=(key,unit='%')=>number(k[key])==null?'Indisponible':`${fmt(k[key],unit==='cas'?0:2)}${unit==='cas'?' cas':unit==='EUR'?' €':' %'}`;
 const missing=number(e.invalid_or_missing_facts)+number(e.orders_without_records);
 const scope=missing>0?`${fmt(missing)} source(s) manquante(s) ou incohérente(s)`:`${fmt(e.production_records)} enregistrements · OF achevés`;
 return [
 ['♧','OTIF',v('otif_pct'),`${fmt(e.otif_lines)} / ${fmt(e.due_customer_lines)} lignes dues`,''],
 ['⚙','OEE',v('oee_pct'),scope,''],
 ['▱','First Pass Yield',v('first_pass_yield_pct'),`${fmt(e.first_pass_good_units)} / ${fmt(e.total_units)} pièces · premier passage`,''],
 ['◎','Cumulative savings',v('cumulative_savings_eur','EUR'),`Cumul net depuis ${d.start_date} · validé`,''],
 ['♧','Scrap rate',v('scrap_rate_pct'),`${fmt(e.scrap_units)} / ${fmt(e.total_units)} pièces · rebut définitif`,''],
 ['▥','Machine availability',v('machine_availability_pct'),`${fmt(e.run_minutes)} / ${fmt(e.planned_minutes)} min · lots mesurés`,''],
 ['⬡','Inventory accuracy',v('inventory_accuracy_pct'),`${fmt(e.accurate_counts)} / ${fmt(e.inventory_counts)} comptages exacts`,''],
 ['♧','Lost-time incidents',v('lost_time_incidents','cas'),`${d.start_date} → ${d.end_date} · cas avec arrêt`,'']];
}
