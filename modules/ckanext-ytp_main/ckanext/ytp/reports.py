from ckan.common import OrderedDict, _
from ckan.logic import get_action, NotFound, NotAuthorized
import itertools
from datetime import timedelta, datetime
import logging

log = logging.getLogger(__name__)

def administrative_branch_summary_report():
    org_names = [
            'ulkoministerio',
            'sisaministerio',
            'liikenne-ja-viestintaministerio',
            'maa-ja-metsatalousministerio',
            'oikeusministerio',
            'opetus-ja-kulttuuriministerio',
            'puolustusministerio',
            'sosiaali-ja-terveysministerio',
            'tyo-ja-elinkeinoministerio',
            'valtioneuvoston-kanslia',
            'valtiovarainministerio',
            'ymparistoministerio',
            ]

    context = {}

    # Optimization opportunity: Could fetch all orgs here and manually create the hierarchy
    orgs = get_action('organization_list')(context, {'organizations': org_names, 'all_fields': True})

    org_trees = [get_action('group_tree_section')(context, {'id': org['id'], 'type': 'organization'})
                 for org in orgs]

    def children(dataset):
        return dataset['children']

    org_levels = {
            org['name']: level
            for t in org_trees
            for org, level in hierarchy_levels(t, children)}

    flat_orgs = (org for t in org_trees for org in flatten(t, children))

    def with_totals(orgs):
        for org in orgs:
            if org_levels[org['name']] == 0:
                total_org = org.copy()
                total_org['total_org'] = True
                yield total_org
            org['total_org'] = False
            yield org

    root_tree_ids_pairs = (
            (r, [x['id'] for x in (flatten(r, children) if r['total_org'] else [r])])
            for r in with_totals(flat_orgs))

    # Optimization opportunity: Prefetch datasets for all related orgs in one go
    root_datasets_pairs = (
            (k, list(package_generator('owner_org:(%s)' % ' OR '.join(v), 1000, context)))
            for k, v in root_tree_ids_pairs)

    return {
            'now': datetime.today().strftime('%d.%m.%Y'),
            'yrs_ago_1': (datetime.today() - timedelta(1 * 365)).strftime('%d.%m.%Y'),
            'yrs_ago_2': (datetime.today() - timedelta(2 * 365)).strftime('%d.%m.%Y'),
            'yrs_ago_3': (datetime.today() - timedelta(3 * 365)).strftime('%d.%m.%Y'),
            'table' : [{
                'organization': org['title'] if not org['total_org'] else org['title'] + "'s administrative branch",
                'level': org_levels[org['name']],
                'total': org['total_org'],
                'dataset_count': len(datasets),
                'dataset_count_1yr': glen(d for d in datasets if age(d) >= timedelta(1 * 365)),
                'dataset_count_2yr': glen(d for d in datasets if age(d) >= timedelta(2 * 365)),
                'dataset_count_3yr': glen(d for d in datasets if age(d) >= timedelta(3 * 365)),
                'new_datasets_month': glen(d for d in datasets if age(d) <= timedelta(30)),
                'new_datasets_6_months': glen(d for d in datasets if age(d) <= timedelta(6 * 30)),
                'resource_formats': resource_formats(datasets),
                'openness_score_avg': openness_score_avg(context, datasets)
                }
                for org, datasets in root_datasets_pairs
                ]
            }

administrative_branch_summary_report_info = {
    'name': 'administrative-branch-summary-report',
    'title': 'Administrative Branch Summary',
    'description': 'Dataset statistics by administrative branch summary',
    'option_defaults': None,
    'option_combinations': None,
    'generate': administrative_branch_summary_report,
    'template': 'report/administrative_branch_summary_report.html',
}

def package_generator(query, page_size, context):
    package_search = get_action('package_search')

    for index in itertools.count(start=0, step=page_size):
        data_dict = {'include_private': True, 'rows': page_size, 'q': query, 'start': index}
        packages = package_search(context, data_dict).get('results', [])
        for package in packages:
            yield package
        else:
            return

def age(dataset):
    return datetime.now() - datetime.strptime(dataset['metadata_created'], '%Y-%m-%dT%H:%M:%S.%f')


def glen(generator):
    '''
    Returns the number of items in a generator without interemediate lists
    '''
    return sum(1 for x in generator)


def flatten(x, children):
    '''
    Flatten a hierarchy into an element iterator
    '''
    yield x
    for child in children(x):
        for cx in flatten(child, children):
            yield cx

def hierarchy_levels(x, children, level=0):
    '''
    Provide hierarchy levels for nodes in a hierarchy
    '''
    yield(x, level)
    for child in children(x):
        for cx, cl in hierarchy_levels(child, children, level + 1):
            yield (cx, cl)

def resource_formats(datasets):
    return ', '.join({r['format'] for d in datasets for r in d['resources'] if r['format']})

def openness_score_avg(context, datasets):
    openness_score = get_action('qa_package_openness_show')
    scores = (openness_score(context, {"id": d['id']}) for d in datasets)
    total, count = reduce(tuple_sum, (
        (s['openness_score'], 1)
        for s in scores
        if s.get('openness_score') is not None),
        (0, 0))
    return total / count if count > 0 else None

def tuple_sum(*xs):
    return tuple(sum(x) for x in zip(*xs))
