"""Convert an OCEL 2.0 JSON log into the sequence log consumed by MultiObjectGraph."""
import pandas as pd


def convert_to_df(d):
    """One row per event: event_id, event_type, timestamp and, per object type,
    the list of related object ids."""
    object_type_of = {o['id']: o['type'] for o in d['objects']}
    object_types = list(dict.fromkeys(object_type_of.values()))

    rows = []
    for e in d['events']:
        row = {'event_id': e['id'], 'event_type': e['type'], 'timestamp': e['time'],
               **{t: [] for t in object_types}}
        for rel in e['relationships']:
            ot = object_type_of.get(rel['objectId'])
            if ot is not None:
                row[ot].append(rel['objectId'])
        rows.append(row)

    event_df = pd.DataFrame(rows, columns=['event_id', 'event_type', 'timestamp', *object_types])
    # '-' is used as a separator in edge keys, so it must not appear in activity names
    event_df['event_type'] = event_df['event_type'].str.replace('-', ' ')
    return event_df


def convert_to_original_eventlog(ocel_event_df, o_types):
    """Classic event log: one row per (object, event)."""
    rows = []
    for _, item in ocel_event_df.iterrows():
        for o_type in o_types:
            for o_id in item[o_type]:
                rows.append({'case_id': o_id, 'object_type': o_type, 'event_id': item['event_id'],
                             'activity': item['event_type'], 'timestamp': item['timestamp']})
    return pd.DataFrame(rows, columns=['case_id', 'object_type', 'event_id', 'activity', 'timestamp'])


def convert_to_stl_log_ocel(eventlog_org_df):
    """Case variants (activity sequence + frequency) and edge weights per object type."""
    df = (eventlog_org_df.sort_values(by=['case_id', 'timestamp'])
          .groupby(['case_id', 'object_type'])['activity']
          .apply(list).reset_index(name='sequence'))
    df['sequence'] = df['sequence'].apply(','.join)
    sequence_df = df.groupby(['sequence', 'object_type'])['case_id'].count().reset_index(name='frequency')

    case_variants, edge_weights = [], []
    for _, item in sequence_df.iterrows():
        sequence = item['sequence'].split(',')
        case_variants.append({'sequence': sequence, 'frequency': item['frequency'],
                              'object_type': item['object_type']})
        for pre, post in zip(sequence, sequence[1:]):
            edge_weights.append({'weight': 1, 'from': pre, 'to': post, 'object_type': item['object_type']})

    return {'case_variants': case_variants, 'edge_weights': edge_weights}


def ocel_to_layout_log(d):
    """OCEL 2.0 JSON dict -> (classic event log DataFrame, layout log dict)."""
    object_types = [e['name'] for e in d['objectTypes']]
    event_df = convert_to_df(d)
    eventlog_org_df = convert_to_original_eventlog(event_df, object_types)
    return eventlog_org_df, convert_to_stl_log_ocel(eventlog_org_df)
