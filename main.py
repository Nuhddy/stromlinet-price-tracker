#! /usr/bin/env python3

import requests
import re
import json
import base64
import csv
import pandas as pd
import plotly.express as px
import plotly.io as pio
from bs4 import BeautifulSoup


def format_hours(hours):
    hour_array = []
    for hour in hours:
        hour_array.append(str(hour).zfill(2))
    return hour_array


def send_get_request(source_url):
    soup = BeautifulSoup(requests.get(source_url).content, 'html.parser')
    iframe = soup.find('iframe')

    html = requests.get(iframe['src']).text  # type: ignore
    d = json.loads(base64.b64decode(iframe['src'].split('=')[-1]).decode('utf-8'))  # type: ignore

    resourceKey = d['k']
    resolvedClusterUri = re.search(r"var resolvedClusterUri = '(.*?)'", html)[1].replace('-redirect', '-api')  # type: ignore
    requestId = re.search(r"var requestId = '(.*?)'", html)[1]  # type: ignore
    activityId = re.search(r"var telemetrySessionId =  '(.*?)'", html)[1]  # type: ignore

    url = resolvedClusterUri + '/public/reports/' + resourceKey + '/modelsAndExploration?preferReadOnlySession=true'
    query_url = resolvedClusterUri + 'public/reports/querydata?synchronous=true'
    headers = {
        'ActivityId': activityId,
        'RequestId': requestId,
        'X-PowerBI-ResourceKey': resourceKey
    }

    data = requests.get(url, headers=headers).json()

    return (data, headers, query_url)


def send_post_request(data, query_url, headers, visualId):
    for s in data['exploration']['sections']:
        for k, _ in enumerate(s['visualContainers']):
            if json.loads(s['visualContainers'][k]['config'])['name'] == visualId:

                query = json.loads(s['visualContainers'][k]['query'])
                query['Commands'][0]['SemanticQueryDataShapeCommand']['Query']['Where'][0]['Condition']['In']['Values'][0][0]['Literal']['Value'] = "'Øst (DK2)'"

                datasetId = data['models'][0]['dbName']
                reportId = data['exploration']['report']['objectId']
                modelId = data['models'][0]['id']

                payload = {
                    'version': '1.0.0',
                    'queries': [{
                        'Query': query,
                        'QueryId': '',
                        'ApplicationContext': {
                            'DatasetId': datasetId,
                            'Sources': [{
                                'ReportId': reportId,
                                'VisualId': visualId
                                }]
                            }
                        }],
                    'cancelQueries': [],
                    'modelId': modelId
                }

                section_data = requests.post(query_url, json=payload, headers=headers).json()
                return section_data


def map_price_data(section_data):
    prices_hourly = []
    for el in section_data['results'][0]['result']['data']['dsr']['DS'][0]['PH'][0]['DM0']:
        hour = int(el['G0'])
        price = float(el['X'][0]['M0'])
        prices_hourly.append([hour, price])
    return prices_hourly


def write_to_csv(data, file):
    fields = ['hour', 'price']
    rows = data

    with open(file, 'w') as f:
        write = csv.writer(f)
        write.writerow(fields)
        write.writerows(rows)


def draw_graph():
    # Draw lineplot
    df = pd.read_csv('out/data.csv')

    lineplot = px.line(
        data_frame=df,
        x='hour',
        y='price',
        title='Hourly energy prices (current date)',
        labels={'hour': 'Hour', 'price': 'Price (øre/kWh)'},
        markers=True,
        template='plotly_dark'
    )

    lineplot.update_layout(
        xaxis={
            'tickmode': 'array',
            'tickvals': df.hour,
            'ticktext': format_hours(df.hour)
        },
        yaxis={
            'rangemode': 'tozero'
        }
    )

    config = {
        'displayModeBar': False,
        'scrollZoom': False
    }

    pio.write_html(
        lineplot,
        file='out/graph.html',
        config=config,
        full_html=False,
        include_plotlyjs='cdn'  # type: ignore
    )


def update_html():
    with open('out/graph.html', 'r') as f:
        graph = f.read()

    html = '''<!DOCTYPE html>
    <html>
    <head>
        <title>Energy Prices</title>
    </head>
    <body style="margin: 0; background: rgb(17, 17, 17);">
    {graph}
    </body>
    </html>'''.format(graph=graph)

    with open('out/index.html', 'w') as f:
        f.write(html)


def main():
    source_url = 'https://stromlinet.dk/'
    visualId = '4f80742e5e70580d0b0b'

    # GET
    get_response = send_get_request(source_url)
    data = get_response[0]
    headers = get_response[1]
    query_url = get_response[2]

    # POST
    section_data = send_post_request(data, query_url, headers, visualId)

    # Write relevant data to csv
    prices_hourly = map_price_data(section_data)
    write_to_csv(prices_hourly, 'out/data.csv')

    # Draw graph
    draw_graph()
    update_html()


if __name__ == '__main__':
    main()
