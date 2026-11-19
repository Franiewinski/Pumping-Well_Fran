"""NVO — módulo inicial de análise de testes de produção em poço único.
Execute: streamlit run app.py
Biblioteca científica: https://geopilot-ai.github.io/pumptest/
"""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='NVO | Teste de bombeamento', page_icon='💧', layout='wide')
st.title('NVO · Teste de bombeamento')
st.caption('Pré-análise técnica de testes de produção em poço único. Estimativas não substituem validação hidrogeológica.')

try:
    from pumptest import cooper_jacob, step_drawdown, theis_recovery
    from pumptest.diagnostics import log_derivative
    HAVE_PUMPTEST = True
except ImportError:
    HAVE_PUMPTEST = False
    st.error('Biblioteca pumptest não instalada. Execute: pip install git+https://github.com/GeoPilot-AI/pumptest')

EXAMPLE = pd.DataFrame({
    'tempo_min':[0,1,2,3,5,7,10,15,20,30,45,60,90,120,180,240,360,480,600,720],
    'nivel_m':[12.0,12.72,13.05,13.28,13.55,13.75,13.91,14.10,14.25,14.44,14.63,14.80,15.00,15.16,15.38,15.55,15.80,15.95,16.10,16.19],
    'vazao_m3h':[36.0]*20,
})

# These methods operate in days, metres, m³/day.
def convert_minutes_to_days(v):
    return np.asarray(v, dtype=float) / 1440.0


def ensure_columns(df):
    required = ['tempo_min','nivel_m']
    missing = [k for k in required if k not in df.columns]
    if missing:
        raise ValueError('Colunas ausentes: ' + ', '.join(missing))
    frame = df.copy()
    for k in ['tempo_min','nivel_m'] + (['vazao_m3h'] if 'vazao_m3h' in frame else []):
        frame[k] = pd.to_numeric(frame[k], errors='coerce')
    frame = frame.dropna(subset=required).sort_values('tempo_min').reset_index(drop=True)
    if frame.empty:
        raise ValueError('Sem medições válidas de tempo e nível.')
    if (frame.tempo_min < 0).any():
        raise ValueError('Tempo negativo no ensaio.')
    if frame.tempo_min.duplicated().any():
        raise ValueError('Tempos duplicados: revisar ou agregar leituras antes da análise.')
    return frame


def method_fit(frame, ne, rate_m3h, start_min, end_min):
    sel = frame[(frame.tempo_min >= start_min)&(frame.tempo_min <= end_min)&(frame.tempo_min > 0)].copy()
    sel['s'] = sel.nivel_m - ne
    sel = sel[sel.s >= 0]
    if len(sel) < 4:
        raise ValueError('É necessário selecionar pelo menos quatro observações válidas para o ajuste exploratório.')
    if rate_m3h <= 0:
        raise ValueError('A vazão deve ser positiva.')
    q_d = rate_m3h * 24.0
    t_d = convert_minutes_to_days(sel.tempo_min.to_numpy())
    cj = cooper_jacob(t_d,sel.s.to_numpy(),rate=q_d,distance=0.075,
                      start=float(t_d[0]))
    # Fitted straight line on semilog plot, independently for plotting and R².
    X = np.log10(sel.tempo_min.to_numpy(dtype=float))
    slope,intercept = np.polyfit(X,sel.s.to_numpy(dtype=float),1)
    prediction = slope*X+intercept
    ssr = np.sum((sel.s.to_numpy()-prediction)**2)
    sst = np.sum((sel.s.to_numpy()-sel.s.mean())**2)
    r2 = (1-ssr/sst) if sst>0 else np.nan
    return cj, sel, float(slope), float(intercept), float(r2)

with st.sidebar:
    st.header('Dados do processo')
    well_id = st.text_input('Identificador do poço', 'Poço exemplo')
    test_date = st.date_input('Data do teste', value=None)
    test_type = st.selectbox('Tipo de ensaio', ['Vazão constante — poço único','Escalonado','Recuperação'])
    st.divider()
    ne = st.number_input('Nível estático, NE (m)', min_value=0., value=12., step=.1,format='%.2f')
    rate = st.number_input('Vazão constante (m³/h)', min_value=0., value=36., step=1.,format='%.2f')
    well_radius = st.number_input('Raio do poço (m), quando conhecido', min_value=0.001, value=0.075,step=.005,format='%.3f')
    declared_T = st.number_input('T declarada (m²/d), 0 = não informado', min_value=0.,value=0.,format='%.2f')
    st.caption('A medição deve utilizar o mesmo referencial vertical do NE; NE e ND são profundidades positivas para baixo.')

st.subheader('Entrada de dados')
up = st.file_uploader('Importar medições (.csv ou .xlsx)',type=['csv','xlsx'])
try:
    if up is None:
        raw = EXAMPLE.copy()
        st.info('Exibindo dados SIMULADOS para testar a interface. Importe sua planilha para analisar um processo.')
    elif up.name.lower().endswith('.xlsx'):
        raw = pd.read_excel(up)
    else:
        payload=up.getvalue()
        try:
            raw=pd.read_csv(io.BytesIO(payload),sep=None,engine='python')
        except Exception:
            raw=pd.read_csv(io.BytesIO(payload),sep=';')
    df = ensure_columns(raw)
except Exception as e:
    st.error(f'Importação inválida: {e}')
    st.stop()

with st.expander('Visualizar / editar medições',expanded=up is None):
    edited=st.data_editor(df,num_rows='dynamic',use_container_width=True)
try:
    df=ensure_columns(edited)
except ValueError as e:
    st.error(str(e)); st.stop()

st.download_button('Modelo CSV',EXAMPLE.head(0).to_csv(index=False).encode(),file_name='modelo_teste_nvo.csv',mime='text/csv')

stabs=st.tabs(['Resumo e consistência','Rebaixamento','Derivada de Bourdet','Interpretação / T','Avaliação técnica'])
obs=df[df.tempo_min>0].copy()
obs['rebaixamento_m']=obs.nivel_m-ne
valid = obs[(obs.rebaixamento_m>=0)&(obs.tempo_min>0)].copy()
q_series=df['vazao_m3h'].dropna() if 'vazao_m3h' in df else pd.Series(dtype=float)
q_variation=(float((q_series.max()-q_series.min())/q_series.mean()*100) if len(q_series)>1 and q_series.mean()>0 else None)
flags=[]
if len(valid)<4: flags.append('Menos de quatro medições positivas válidas; interpretação de curva insuficiente.')
if (obs.rebaixamento_m<0).any(): flags.append('Há níveis menores que o NE (rebaixamento negativo); conferir referencial, medições e fase do teste.')
if rate<=0: flags.append('Vazão constante não informada.')
if q_variation is not None and q_variation>5: flags.append('Variação de vazão superior a 5% (alerta configurável, não um limite normativo); análise com Q constante pode ser inadequada.')
if df.tempo_min.max()==0: flags.append('Não há medições após o início do bombeamento.')

with stabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Medições válidas',len(valid))
    c2.metric('Duração registrada',f'{df.tempo_min.max():.0f} min')
    c3.metric('Rebaixamento final',f'{obs.rebaixamento_m.iloc[-1]:.2f} m' if len(obs) else '—')
    specific=(rate/obs.rebaixamento_m.iloc[-1] if len(obs) and obs.rebaixamento_m.iloc[-1]>0 else None)
    c4.metric('Capacidade específica',f'{specific:.2f} m³/h/m' if specific is not None else '—')
    if q_variation is not None: st.write(f'Oscilação relativa da vazão observada (amplitude/média): **{q_variation:.1f}%**')
    if flags:
        for f in flags: st.warning(f)
    else: st.success('Sem inconsistências básicas detectadas. Isso não equivale à validação hidrogeológica do ensaio.')

with stabs[1]:
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=valid.tempo_min,y=valid.rebaixamento_m,mode='lines+markers',name='Rebaixamento medido'))
    fig.update_layout(xaxis_title='Tempo de bombeamento (min)',yaxis_title='Rebaixamento (m)',height=440)
    st.plotly_chart(fig,use_container_width=True)
    fig2=go.Figure()
    fig2.add_trace(go.Scatter(x=valid.tempo_min,y=valid.rebaixamento_m,mode='lines+markers',name='Medido'))
    fig2.update_layout(xaxis_type='log',xaxis_title='Tempo (min, log10)',yaxis_title='Rebaixamento (m)',height=420)
    st.plotly_chart(fig2,use_container_width=True)

with stabs[2]:
    st.write('Derivada logarítmica de Bourdet **ds/d(ln t)**, calculada sobre as medições do ensaio.')
    window=st.slider('Janela de suavização (unidades de ln t)',0.1,0.5,0.2,0.05)
    if HAVE_PUMPTEST and len(valid)>=4:
        try:
            t=convert_minutes_to_days(valid.tempo_min.to_numpy(dtype=float))
            s=valid.rebaixamento_m.to_numpy(dtype=float)
            td,dd=log_derivative(t,s,window=window)
            td=np.asarray(td)*1440
            dd=np.asarray(dd)
            diag=go.Figure()
            diag.add_trace(go.Scatter(x=valid.tempo_min,y=valid.rebaixamento_m,mode='markers+lines',name='Rebaixamento'))
            mask=(np.asarray(dd)>0)&np.isfinite(dd)
            diag.add_trace(go.Scatter(x=td[mask],y=dd[mask],mode='markers+lines',name='Derivada de Bourdet'))
            diag.update_layout(xaxis_type='log',yaxis_type='log',xaxis_title='Tempo (min, log)',yaxis_title='s e ds/d(ln t) (m, log)',height=480)
            st.plotly_chart(diag,use_container_width=True)
            if not mask.all(): st.warning('Foram omitidos valores não positivos/não finitos da derivada no gráfico log-log.')
            st.caption('Uma derivada horizontal pode sugerir fluxo radial; a interpretação exige avaliação dos efeitos do poço e dos dados de vazão.')
        except Exception as e:
            st.warning(f'Não foi possível calcular a derivada: {e}')
    else: st.info('A derivada requer pelo menos quatro medições válidas e pumptest instalada.')

with stabs[3]:
    st.write('**Cooper-Jacob:** ajuste exploratório de um trecho selecionado da curva semilogarítmica.')
    st.warning('Poço único: armazenamento do poço, skin e perdas de carga podem afetar o resultado. O ajuste não comprova, sozinho, fluxo radial nem determina S confiável.')
    if test_type!='Vazão constante — poço único':
        st.info('Esta primeira versão aplica Cooper-Jacob somente a ensaios declarados de vazão constante. Para escalonados e recuperação, consulte a aba de avaliação técnica.')
    elif HAVE_PUMPTEST and len(valid)>=4 and rate>0:
        left,right=st.columns(2)
        min_t,max_t=float(valid.tempo_min.min()),float(valid.tempo_min.max())
        start=left.number_input('Início do trecho (min)',value=float(valid.tempo_min.iloc[max(0,len(valid)//3)]),min_value=min_t,max_value=max_t)
        end=right.number_input('Fim do trecho (min)',value=max_t,min_value=min_t,max_value=max_t)
        if end<=start: st.warning('O fim precisa ser posterior ao início.')
        else:
            try:
                cj,sel,slope,intercept,r2=method_fit(valid,ne,rate,start,end)
                st.metric('T estimada — Cooper-Jacob',f'{cj.transmissivity:.2f} m²/d')
                st.write(f'Inclinação semilog: **{slope:.3f} m/ciclo** · R² do trecho: **{r2:.3f}** · {len(sel)} pontos selecionados')
                x=np.geomspace(start,end,100)
                fig=go.Figure()
                fig.add_trace(go.Scatter(x=valid.tempo_min,y=valid.rebaixamento_m,mode='markers',name='Medições'))
                fig.add_trace(go.Scatter(x=x,y=intercept+slope*np.log10(x),name='Reta ajustada no trecho'))
                fig.update_layout(xaxis_type='log',xaxis_title='Tempo (min, log10)',yaxis_title='Rebaixamento (m)',height=420)
                st.plotly_chart(fig,use_container_width=True)
                if declared_T>0:
                    delta=(cj.transmissivity-declared_T)/declared_T*100
                    st.write(f'T declarada: **{declared_T:.2f} m²/d** · Diferença: **{delta:+.1f}%**')
                st.caption('T é uma estimativa condicionada à adequação do regime de fluxo e às hipóteses do método. R² alto não garante modelo hidrogeológico correto.')
            except Exception as e:
                st.warning(f'Não foi possível ajustar o trecho: {e}')
    else: st.info('Dados insuficientes para o ajuste.')

with stabs[4]:
    st.subheader('Conclusão preliminar')
    st.write(f'**Poço:** {well_id}  ·  **Tipo:** {test_type}')
    st.write(f'Foram recebidas {len(df)} medições, com duração de {df.tempo_min.max():.0f} minutos e NE declarado de {ne:.2f} m.')
    if flags:
        for f in flags: st.write('• '+f)
    if test_type=='Escalonado':
        st.info('Próxima etapa: selecionar finais de cada estágio e aplicar step_drawdown(Q, s); somente estágios comparáveis permitem interpretar B e C.')
    elif test_type=='Recuperação':
        st.info('Próxima etapa: receber duração do bombeamento, tempo desde desligamento e rebaixamento residual; aplicar theis_recovery.')
    else:
        st.write('A derivada é usada para identificar regimes candidatos e auxiliar na seleção do trecho de ajuste; a aprovação técnica permanece com a analista.')
    st.caption('O módulo não conclui regularidade normativa do teste automaticamente. A verificação depende dos requisitos aplicáveis ao processo.')
    export=df.copy()
    export['rebaixamento_m']=export.nivel_m-ne
    st.download_button('Exportar medições e rebaixamento (CSV)',export.to_csv(index=False).encode('utf-8-sig'),file_name='nvo_teste_processado.csv',mime='text/csv')
