import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import requests, os
from gwpy.timeseries import TimeSeries
from gwosc.locate import get_urls
from gwosc import datasets
from gwosc.api import fetch_event_json

from copy import deepcopy
import base64

from helper import make_audio_file

# Use the non-interactive Agg backend, which is recommended as a
# thread-safe backend.
# See https://matplotlib.org/3.3.2/faq/howto_faq.html#working-with-threads.
import matplotlib as mpl
mpl.use("agg")

##############################################################################
# Workaround for the limited multi-threading support in matplotlib.
# Per the docs, we will avoid using `matplotlib.pyplot` for figures:
# https://matplotlib.org/3.3.2/faq/howto_faq.html#how-to-use-matplotlib-in-a-web-application-server.
# Moreover, we will guard all operations on the figure instances by the
# class-level lock in the Agg backend.
##############################################################################

# -- Set page config
apptitle = 'GW Quickview'

st.set_page_config(page_title=apptitle, page_icon=":eyeglasses:")

# -- Default detector list
detectorlist = ['H1','L1', 'V1']

# Title the app
st.title('Visualização Rápida de Ondas Gravitacionais')

st.markdown("""
 * Use the menu at left to select data and set plot parameters
 * Your plots will appear below
""")

@st.cache_data(max_entries=5)   #-- Magic command to cache data
def load_gw(t0, detector, fs=4096):
    strain = TimeSeries.fetch_open_data(detector, t0-14, t0+14, sample_rate = fs, cache=False)
    return strain

@st.cache_data(max_entries=10)   #-- Magic command to cache data
def get_eventlist():
    allevents = datasets.find_datasets(type='events')

    # Drop the version number and filter for GW events
    commonev = [ev.split('-')[0] for ev in allevents if ev.startswith("GW")]

    # Drop duplicates and sort
    eventlist = list(set(commonev))
    eventlist.sort()    
    return eventlist
    
st.sidebar.markdown("## Select Data Time and Detector")

# -- Get list of events
eventlist = get_eventlist()

#-- Set time by GPS or event
select_event = st.sidebar.selectbox('Como você deseja localizar os dados?',
                                    ['Pelo nome do evento', 'Pelo GPS'], key='datatype')

if select_event == 'Pelo GPS':
    # -- Set a GPS time:        
    str_t0 = st.sidebar.text_input('Tempo GPS', '1126259462.4', key='gpstime')    # -- GW150914
    t0 = float(str_t0)

    st.sidebar.markdown("""
    Exemplos de instantes de observação no detector H1:
    * 1126259462.4    (GW150914) 
    * 1187008882.4    (GW170817) 
    * 1128667463.0    (injeção de hardware)
    * 1132401286.33   (Koi Fish Glitch) 
    """)

else:
    chosen_event = st.sidebar.selectbox('Event selecionado', eventlist, key='eventchoice')
    t0 = datasets.event_gps(chosen_event)
    detectorlist = list(datasets.event_detectors(chosen_event))
    detectorlist.sort()
    st.subheader(chosen_event)
    st.write('GPS:', t0)
    
    # -- Experiment to display masses
    try:
        jsoninfo = fetch_event_json(chosen_event)
        for name, nameinfo in jsoninfo['events'].items():        
            st.write('Massa 1:', nameinfo['mass_1_source'], 'M$_{\odot}$')
            st.write('Massa 2:', nameinfo['mass_2_source'], 'M$_{\odot}$')
            st.write('Network SNR:', int(nameinfo['network_matched_filter_snr']))
            eventurl = 'https://gwosc.org/eventapi/html/event/{}'.format(chosen_event)
            st.markdown('Página do Evento: {}'.format(eventurl))
            st.write('\n')
    except:
        pass

    
#-- Choose detector as H1, L1, or V1
detector = st.sidebar.selectbox('Detector', detectorlist, key='ifochoice')

# -- Select for high sample rate data
fs = 4096
maxband = 1200
high_fs = st.sidebar.checkbox('Dados com a taxa de amostragem original', key='samplerate')
if high_fs:
    fs = 16384
    maxband = 2000


# -- Create sidebar for plot controls
st.sidebar.markdown('## Configurar os parâmetros do gráfico')
dtboth = st.sidebar.slider('Intervalo de tempo (segundos)', 0.1, 8.0, 1.0, key='timerange')  # min, max, default
dt = dtboth / 2.0

st.sidebar.markdown('#### Dados branqueados e filtrados por passa-banda')
whiten = st.sidebar.checkbox('Branquear os dados??', value=True)
freqrange = st.sidebar.slider('Faixa de frequências do filtro passa-banda (Hz)', min_value=10, max_value=maxband, value=(30,400), key='bandpass')


# -- Create sidebar for Q-transform controls
st.sidebar.markdown('#### Gráfico da transformada Q')
vmax = st.sidebar.slider('Energia máxima da barra de cores', 10, 500, 25, key='colorrange')  # min, max, default
qcenter = st.sidebar.slider('Q-value', 5, 120, 5, key='qvalue')  # min, max, default
qrange = (int(qcenter*0.8), int(qcenter*1.2))

#-- Create a text element and let the reader know the data is loading.
strain_load_state = st.text('Carregando os dados... Isso pode levar cerca de um minuto.')
try:
    strain_data = load_gw(t0, detector, fs)
except:
    st.warning('{0} Não há dados disponíveis para o instante selecionado. {1}.  Tente selecionar outra combinação de instante de observação e detector.'.format(detector, t0))
    st.stop()
    
strain_load_state.text('Carregamento dos dados concluído!')

#-- Make a time series plot

cropstart = t0-0.2
cropend   = t0+0.1

cropstart = t0 - dt
cropend   = t0 + dt

st.subheader('Dados brutos')
center = int(t0)
strain = deepcopy(strain_data)

fig1 = strain.crop(cropstart, cropend).plot()
st.pyplot(fig1, clear_figure=True)

# -- Try whitened and band-passed plot
# -- Whiten and bandpass data
st.subheader('Dados branqueados e filtrados por passa-banda')

minfreq=freqrange[0]
maxfreq=freqrange[1]+2 # Add 2 to avoid minfreq = maxfreq

if whiten:
    white_data = strain.whiten()
    bp_data = white_data.bandpass(minfreq, maxfreq)
else:
    bp_data = strain.bandpass(minfreq, maxfreq)

bp_cropped = bp_data.crop(cropstart, cropend)

fig3 = bp_cropped.plot()
st.pyplot(fig3, clear_figure=True)

# -- Allow data download
download = {'Tempo':bp_cropped.times, 'Strain':bp_cropped.value}
df = pd.DataFrame(download)
csv = df.to_csv(index=False)
b64 = base64.b64encode(csv.encode()).decode()  # some strings <-> bytes conversions necessary here
fn =  detector + '-STRAIN' + '-' + str(int(cropstart)) + '-' + str(int(cropend-cropstart)) + '.csv'
href = f'<a href="data:file/csv;base64,{b64}" download="{fn}">Download Dados como arquivo CSV</a>'
st.markdown(href, unsafe_allow_html=True)

# -- Make audio file
st.audio(make_audio_file(bp_cropped), format='audio/wav')

# -- Notes on whitening
with st.expander("Veja as notas"):
    st.markdown("""
 * O branqueamento (whitening) é um processo que ajusta os pesos das componentes de frequência de um sinal, de modo que o ruído apresente aproximadamente a mesma intensidade em todas as faixas de frequência.
 * Um filtro passa-banda (band-pass filter) utiliza duas frequências de corte, uma inferior e outra superior, permitindo a passagem apenas das componentes do sinal cujas frequências estejam dentro dessa faixa.

Veja também:
 * [Tutorial de processamento de sinais](https://share.streamlit.io/jkanner/streamlit-audio/main/app.py)
""")


st.subheader('Transformada Q')

try:
    hq = strain.q_transform(outseg=(t0-dt, t0+dt), qrange=qrange)
    fig4 = hq.plot()
    ax = fig4.gca()
    fig4.colorbar(label="Energia Normalizada", vmax=vmax, vmin=0)
    ax.grid(False)
    ax.set_yscale('log')
    ax.set_ylim(bottom=15)
    st.pyplot(fig4, clear_figure=True)
except:
    st.markdown("Não foi possível gerar a transformada Q para esses dados.")

with st.expander("Veja as notas"):

    st.markdown("""
Um gráfico da transformada Q mostra como a frequência de um sinal varia ao longo do tempo.

* O eixo horizontal (x) representa o tempo.
* O eixo vertical (y) representa a frequência.

A escala de cores representa a quantidade de energia ou potência do sinal em cada elemento (pixel) do plano tempo-frequência.

Um parâmetro denominado Q corresponde ao fator de qualidade. Quanto maior o fator de qualidade, maior o número de ciclos do sinal contidos em cada elemento do plano tempo-frequência.

Na análise de sinais de ondas gravitacionais, os sinais produzidos pela fusão de sistemas binários de buracos negros são geralmente mais bem visualizados com valores menores de Q (Q=5 a 20), enquanto os sinais de fusões de estrelas de nêutrons em sistemas binários são mais bem representados com valores maiores de Q (Q=80 a 120).

Veja também:

 * [Transformada Q GWpy](https://gwpy.github.io/docs/latest/examples/timeseries/qscan/)
 * [Interpretando gráficos de tempo-frequência](https://labcit.ligo.caltech.edu/~jkanner/aapt/web/math.html#tfplot)
 * [Shourov Chatterji PhD Thesis](https://dspace.mit.edu/handle/1721.1/34388)
""")


st.subheader("Sobre esse aplicativo")
st.markdown("""
Este aplicativo exibe dados dos detectores LIGO, Virgo e GEO, 
baixados do Gravitational Wave Open Science Center (GWOSC), disponível em: https://gwosc.org .


Você pode ver como isso funciona no... [Quickview Jupyter Notebook](https://github.com/losc-tutorial/quickview) ou 
[veja o código](https://github.com/jkanner/streamlit-dataview).

""")
