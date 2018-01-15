import ast
import datetime
import json
import logging
import pylons
import pylons.config as config
import re
import types
import urllib2
import urlparse
import validators

import ckan.lib.base as base
import ckan.logic.schema
from ckan import authz as authz
from ckan import plugins, model, logic, authz
from ckan.common import _, c, request
from ckan.config.routing import SubMapper
from ckan.lib import helpers
from ckan.lib.dictization import model_dictize
from ckan.lib.munge import munge_title_to_name
from ckan.lib.navl import dictization_functions
from ckan.lib.navl.dictization_functions import Missing, StopOnError, missing, flatten_dict, unflatten, Invalid
from ckan.lib.plugins import DefaultOrganizationForm, DefaultTranslation
from ckan.logic import NotFound, NotAuthorized, auth as ckan_auth, get_action, NotFound
from ckan.model import Session
from ckan.plugins import toolkit
from ckanext.harvest.model import HarvestObject
from ckanext.report.interfaces import IReport
from ckanext.spatial.interfaces import ISpatialHarvester

from paste.deploy.converters import asbool
from sqlalchemy.sql.expression import or_
from webhelpers.html import escape
from webhelpers.html.builder import literal
from webhelpers.html.tags import link_to, literal

import tools
import auth
import menu
import logic

from converters import to_list_json, from_json_list, is_url, convert_to_tags_string, string_join, date_validator, simple_date_validate
from helpers import extra_translation, render_date, get_dict_tree_from_json, service_database_enabled, get_json_value, sort_datasets_by_state_priority, get_facet_item_count, get_remaining_facet_item_count, sort_facet_items_by_name, get_sorted_facet_items_dict, calculate_dataset_stars, get_upload_size, get_license, get_visits_for_resource, get_visits_for_dataset, get_geonetwork_link, calculate_metadata_stars, get_tooltip_content_types, unquote_url, sort_facet_items_by_count, scheming_field_only_default_required, add_locale_to_source, scheming_language_text_or_empty, get_lang_prefix, call_toolkit_function
from tools import add_languages_modify, add_languages_show, add_translation_show_schema, add_translation_modify_schema, get_original_method, create_system_context, get_original_method, add_translation_show_schema, add_languages_show, add_translation_modify_schema, add_languages_modify

try:
    from collections import OrderedDict  # 2.7
except ImportError:
    from sqlalchemy.util import OrderedDict

# This plugin is designed to work only these versions of CKAN
plugins.toolkit.check_ckan_version(min_version='2.0')

abort = base.abort
log = logging.getLogger(__name__)


OPEN_DATA = 'Open Data'
INTEROPERABILITY_TOOLS = 'Interoperability Tools'
PUBLIC_SERVICES = 'Public Services'



class YtpMainTranslation(DefaultTranslation):

    def i18n_domain(self):
        return "ckanext-ytp_main"

def create_vocabulary(name):
    user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})
    context = {'user': user['name']}

    try:
        data = {'id': name}
        v = toolkit.get_action('vocabulary_show')(context, data)
        log.info( name + " vocabulary already exists, skipping.")
    except NotFound:
        log.info("Creating vocab '" + name + "'")
        data = {'name': name}
        v = toolkit.get_action('vocabulary_create')(context, data)

    return v

def create_tag_to_vocabulary(tag, vocab):
    user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})
    context = {'user': user['name']}

    try:
        data = {'id': vocab}
        v = toolkit.get_action('vocabulary_show')(context, data)

    except NotFound:
        log.info("Creating vocab '" + vocab + "'")
        data = {'name': vocab}
        v = toolkit.get_action('vocabulary_create')(context, data)

    data = {
        "name": tag,
        "vocabulary_id": v['id']}

    context['defer_commit'] = True
    toolkit.get_action('tag_create')(context, data)

def _escape(value):
    return escape(unicode(value))


def _prettify(field_name):
    """ Taken from ckan.logic.ValidationError.error_summary """
    field_name = re.sub('(?<!\w)[Uu]rl(?!\w)', 'URL', field_name.replace('_', ' ').capitalize())
    return _(field_name.replace('_', ' '))


def _format_value(value):
    if isinstance(value, types.DictionaryType):
        value_buffer = []
        for key, item_value in value.iteritems():
            value_buffer.append(_dict_formatter(key, item_value))
        return value_buffer
    elif isinstance(value, types.ListType):
        value_buffer = []
        for item_value in value:
            value_buffer.append(_format_value(item_value))
        return value_buffer

    return _escape(value)


def _format_extras(extras):

    if not extras:
        return ""
    extra_buffer = {}
    for extra_key, extra_value in extras.iteritems():
        extra_buffer.update(_dict_formatter(extra_key, extra_value))
    return extra_buffer


def _dict_formatter(key, value):

    value_formatter = _key_functions.get(key)
    if value_formatter:
        return value_formatter(key, value)
    else:
        value = _format_value(value)
    if key and value:
        return{key: value}
    return {}


def _parse_extras(key, extras):
    extras_dict = dict()
    if not key or not extras:
        log.error("Fail at Extras key: " + repr(key))
        log.error("Fail Extras payload: " + repr(extras))
        return extras_dict
    for extra in extras:
        key = extra.get('key')
        value = extra.get('value')
        extras_dict.update(_dict_formatter(key, value))
    return extras_dict


def set_empty_if_missing(value, context):
    return value if value else u""


def set_to_user_name(value, context):
    return context['auth_user_obj'].display_name


def set_to_user_email(value, context):
    return context['auth_user_obj'].email


def not_value(text_value):
    def callback(key, data, errors, context):
        value = data.get(key)
        if value == text_value:
            errors[key].append(_('Missing value'))
            raise StopOnError
    return callback


def not_empty_or(item):
    def callback(key, data, errors, context):
        value = data.get(key)
        if value == "":
            # tag_string is converted to tags, so we need check if value is given as empty
            errors[key].append(_('Missing value'))
            raise StopOnError
        elif not value or value is missing:
            value = data.get((item, 0, u'name'), None)
            if not value or value is missing:
                errors[key].append(_('Missing value'))
            else:
                data.pop(key, None)
            raise StopOnError
    return callback

_key_functions = {u'extras': _parse_extras}


@logic.side_effect_free
def action_package_show(context, data_dict):
    result = get_original_method('ckan.logic.action.get', 'package_show')(context, data_dict)
    organization_data = result.get('organization', None)
    if organization_data:
        organization_id = organization_data.get('id', None)
        if organization_id:
            group = model.Group.get(organization_id)
            result['organization'].update(group.extras)

    return result


class YTPDatasetForm(plugins.SingletonPlugin, toolkit.DefaultDatasetForm, YtpMainTranslation):
    plugins.implements(plugins.interfaces.IFacets, inherit=True)
    plugins.implements(plugins.IDatasetForm, inherit=True)
    plugins.implements(plugins.IConfigurer, inherit=True)
    plugins.implements(plugins.IRoutes, inherit=True)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.ITranslation)

    _collection_mapping = {None: ("package/ytp/new_select.html", 'package/new_package_form.html'),
                           OPEN_DATA: ('package/new.html', 'package/new_package_form.html'),
                           INTEROPERABILITY_TOOLS: ('package/new.html', 'package/new_package_form.html')}

    _localized_fields = ['title', 'notes', 'copyright_notice']

    _key_exclude = ['resources', 'organization', 'copyright_notice', 'license_url', 'name',
                    'version', 'state', 'notes', 'tags', 'title', 'collection_type', 'license_title', 'extra_information',
                    'maintainer', 'author', 'owner', 'num_tags', 'owner_org', 'type', 'license_id', 'num_resources',
                    'temporal_granularity', 'temporal_coverage_from', 'temporal_coverage_to', 'update_frequency']

    _key_exclude_resources = ['description', 'name', 'temporal_coverage_from', 'temporal_coverage_to', 'url_type',
                              'mimetype', 'resource_type', 'mimetype_inner', 'update_frequency', 'last_modified',
                              'format', 'temporal_granularity', 'url', 'webstore_url', 'position', 'created',
                              'webstore_last_updated', 'cache_url', 'cache_last_updated', 'size']

    auto_author = False

    # IConfigurable #

    def configure(self, config):
        self.auto_author = asbool(config.get('ckanext.ytp.auto_author', False))

    # ITranslation #

    def i18n_domain(self):
        return "ckanext-ytp_main"

    # IRoutes #

    def before_map(self, m):
        """ CKAN autocomplete discards vocabulary_id from request. Create own api for this. """
        controller = 'ckanext.ytp.controller:YtpDatasetController'
        m.connect('/ytp-api/1/util/tag/autocomplete', action='ytp_tag_autocomplete',
                  controller=controller,
                  conditions=dict(method=['GET']))
        m.connect('/dataset/new_metadata/{id}', action='new_metadata', controller=controller)  # override metadata step at new package
        #m.connect('dataset_edit', '/dataset/edit/{id}', action='edit', controller=controller, ckan_icon='edit')
        #m.connect('new_resource', '/dataset/new_resource/{id}', action='new_resource', controller=controller, ckan_icon='new')
        m.connect('resource_edit', '/dataset/{id}/resource_edit/{resource_id}', action='resource_edit', controller=controller, ckan_icon='edit')

        # Mapping of new dataset is needed since, remapping on read overwrites it
        m.connect('add dataset', '/dataset/new', controller='package', action='new')
        m.connect('/dataset/{id}.{format}', action='read', controller=controller)
        m.connect('related_new', '/dataset/{id}/related/new', action='new_related', controller=controller)
        m.connect('related_edit', '/dataset/{id}/related/edit/{related_id}',
                  action='edit_related', controller=controller)
        #m.connect('dataset_read', '/dataset/{id}', action='read', controller=controller, ckan_icon='sitemap')
        m.connect('/api/util/dataset/autocomplete_by_collection_type', action='autocomplete_packages_by_collection_type', controller=controller)
        return m

    # IConfigurer #

    def update_config(self, config):
        toolkit.add_public_directory(config, '/var/www/resources')
        toolkit.add_resource('public/javascript/', 'ytp_dataset_js')
        toolkit.add_template_directory(config, 'templates')

        toolkit.add_resource('public/javascript/', 'ytp_common_js')
        toolkit.add_template_directory(config, '../common/templates')

    # IDatasetForm #

    def _modify_package_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_to_extras = toolkit.get_converter('convert_to_extras')
        not_empty = toolkit.get_validator('not_empty')
        schema = add_translation_modify_schema(schema)

        schema.update({'copyright_notice': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'collection_type': [not_empty, unicode, convert_to_extras]})
        schema.update({'extra_information': [ignore_missing, is_url, to_list_json, convert_to_extras]})
        schema.update({'valid_from': [ignore_missing, date_validator, convert_to_extras]})
        schema.update({'valid_till': [ignore_missing, date_validator, convert_to_extras]})
        schema.update({'content_type': [not_empty, convert_to_tags_string('content_type')]})

        schema.update({'original_language': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'translations': [ignore_missing, to_list_json, convert_to_extras]})

        schema.update({'owner': [set_empty_if_missing, unicode, convert_to_extras]})
        schema.update({'maintainer': [set_empty_if_missing, unicode]})
        schema.update({'maintainer_email': [set_empty_if_missing, unicode]})

        res_schema = schema.get('resources')
        res_schema.update({'temporal_coverage_from': [ignore_missing, simple_date_validate],
                           'temporal_coverage_to': [ignore_missing, simple_date_validate]})
        schema.update({'resources': res_schema})
        schema = add_languages_modify(schema, self._localized_fields)

        if not self.auto_author or c.userobj.sysadmin:
            schema.update({'author': [set_empty_if_missing, unicode]})
            schema.update({'author_email': [set_empty_if_missing, unicode]})
        else:
            schema.update({'author': [set_to_user_name, ignore_missing, unicode]})
            schema.update({'author_email': [set_to_user_email, ignore_missing, unicode]})

        # Override CKAN schema
        schema.update({'title': [not_empty, unicode]})
        schema.update({'notes': [not_empty, unicode]})
        schema.update({'license_id': [not_empty, not_value('notspecified'), unicode]})

        tag_string_convert = toolkit.get_validator('tag_string_convert')
        schema.update({'tag_string': [not_empty_or('tags'), tag_string_convert]})

        return schema

    def create_package_schema(self):
        schema = super(YTPDatasetForm, self).create_package_schema()
        return self._modify_package_schema(schema)

    def update_package_schema(self):
        schema = super(YTPDatasetForm, self).update_package_schema()
        return self._modify_package_schema(schema)

    def show_package_schema(self):
        schema = super(YTPDatasetForm, self).show_package_schema()

        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_from_extras = toolkit.get_converter('convert_from_extras')

        schema['tags']['__extras'].append(toolkit.get_converter('free_tags_only'))

        schema.update({'copyright_notice': [convert_from_extras, ignore_missing]})
        schema.update({'collection_type': [convert_from_extras, ignore_missing]})
        schema.update({'extra_information': [convert_from_extras, from_json_list, ignore_missing]})
        schema.update({'valid_from': [convert_from_extras, ignore_missing]})
        schema.update({'valid_till': [convert_from_extras, ignore_missing]})
        schema.update({'temporal_granularity': [convert_from_extras, ignore_missing]})
        schema.update({'update_frequency': [convert_from_extras, ignore_missing]})
        schema.update({'content_type': [toolkit.get_converter('convert_from_tags')('content_type'), string_join, ignore_missing]})
        schema.update({'owner': [convert_from_extras, ignore_missing]})

        schema = add_translation_show_schema(schema)
        schema = add_languages_show(schema, self._localized_fields)

        return schema

    def package_types(self):
        return []

    def is_fallback(self):
        return True

    def _get_collection_type(self):
        """Gets the type of collection (Open Data, Interoperability Tools, or Public Services).

        This method can be used to identify which collection the user is currently looking at or editing, i.e., which page the user is on.
        """
        collection_type = request.params.get('collection_type', None)
        if not collection_type and c.pkg_dict and 'collection_type' in c.pkg_dict:
            collection_type = c.pkg_dict['collection_type']
        return collection_type

    def _get_from_mapping(self, index):
        # Get the collection type so that we know which template to show
        collection_type = self._get_collection_type()

        template = self._collection_mapping.get(collection_type, None)
        if not template:
            c.unknown_collection = True
            return self._collection_mapping.get(None)[index]
        return template[index]

    def new_template(self):
        return self._get_from_mapping(0)

    def package_form(self):
        return self._get_from_mapping(1)

    def setup_template_variables(self, context, data_dict):
        c.preselected_group = request.params.get('group', None)
        try:
            super(YTPDatasetForm, self).setup_template_variables(context, data_dict)
        except Exception as e:
            if 'file:///srv/ytp/files/ckan/license.json' in e.message:
                log.info(e)
                pass
            else:
                raise

    # IFacets #

    def dataset_facets(self, facets_dict, package_type):
        facets_dict = OrderedDict()
        facets_dict.update({'collection_type': _('Collection Type')})
        facets_dict.update({'tags': _('Tags')})
        facets_dict.update({'vocab_content_type': _('Content Type')})
        facets_dict.update({'organization': _('Organization')})
        facets_dict.update({'res_format': _('Formats')})
        # BFW: source is not part of the schema. created artificially at before_index function
        facets_dict.update({'source': _('Source')})
        # add more dataset facets here
        return facets_dict

    def group_facets(self, facets_dict, group_type, package_type):
        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):

        facets_dict = OrderedDict()
        facets_dict.update({'collection_type': _('Collection Type')})
        facets_dict.update({'tags': _('Tags')})
        facets_dict.update({'vocab_content_type': _('Content Type')})
        facets_dict.update({'res_format': _('Formats')})

        return facets_dict

    # ITemplateHelpers #

    def format_extras(self, extras):
        return _format_extras(extras)

    def _clean_extras(self, extras):
        extra_dict = {}
        for key in extras:
            if key not in self._key_exclude:
                value = extras.get(key)
                if value:
                    extra_dict.update({_prettify(key): value})
        return extra_dict

    def _clean_extras_resources(self, extras):
        extra_dict = {}
        for key in extras:
            if key not in self._key_exclude_resources:
                value = extras.get(key)
                if value:
                    extra_dict.update({_prettify(key): value})
        return extra_dict

    def _unique_formats(self, resources):
        formats = set()
        for resource in resources:
            formats.add(resource.get('format'))
        formats.discard('')
        return formats

    def _current_user(self):
        return c.userobj

    def _get_user_by_id(self, user_id):
        if not user_id:
            return None
        else:
            user = model.User.get(user_id)
            return user.name

    def _get_user(self, user):
        if not isinstance(user, model.User):
            user_name = unicode(user)
            user = model.User.get(user_name)
            if not user:
                return user_name
        if user:
            name = user.name if model.User.VALID_NAME.match(user.name) else user.id
            display_name = user.display_name
            url = helpers.url_for(controller='user', action='read', id=name)
            return {'name': name, 'display_name': display_name, 'url': url}

    def _dataset_licenses(self):
        licenses_list = [(u'Creative Commons CCZero 1.0', u'cc-zero-1.0'),
                         (u'Creative Commons Attribution 4.0 ', u'cc-by-4.0'),
                         (_('Other'), u'other')]

        return licenses_list

    def _locales_offered(self):
        return config.get('ckan.locales_offered', '').split()

    def _is_list(self, value):
        return isinstance(value, list)

    def _get_package(self, package):
        return toolkit.get_action('package_show')({'model': model}, {'id': package})

    def _resource_display_name(self, resource_dict):
        """ taken from helpers.resource_display_name """
        value = helpers.resource_display_name(resource_dict)
        return value if value != _("Unnamed resource") else _("Additional Info")

    def _auto_author_set(self):
        return self.auto_author

    def _is_sysadmin(self):
        if c.userobj:
            return c.userobj.sysadmin
        return False

    def _is_loggedinuser(self):
        return authz.auth_is_loggedin_user()

    def get_helpers(self):
        return {'current_user': self._current_user,
                'dataset_licenses': self._dataset_licenses,
                'get_user': self._get_user,
                'unique_formats': self._unique_formats,
                'locales_offered': self._locales_offered,
                'is_list': self._is_list,
                'format_extras': self.format_extras,
                'extra_translation': extra_translation,
                'service_database_enabled': service_database_enabled,
                'clean_extras': self._clean_extras,
                'clean_extras_resources': self._clean_extras_resources,
                'get_package': self._get_package,
                'resource_display_name': self._resource_display_name,
                'auto_author_set': self._auto_author_set,
                'get_json_value': get_json_value,
                'sort_datasets_by_state_priority': sort_datasets_by_state_priority,
                'get_facet_item_count': get_facet_item_count,
                'get_remaining_facet_item_count': get_remaining_facet_item_count,
                'sort_facet_items_by_name': sort_facet_items_by_name,
                'sort_facet_items_by_count': sort_facet_items_by_count,
                'get_sorted_facet_items_dict': get_sorted_facet_items_dict,
                'calculate_dataset_stars': calculate_dataset_stars,
                'calculate_metadata_stars': calculate_metadata_stars,
                'is_sysadmin': self._is_sysadmin,
                'is_loggedinuser': self._is_loggedinuser,
                'get_upload_size': get_upload_size,
                'render_date': render_date,
                'get_license': get_license,
                'get_visits_for_resource': get_visits_for_resource,
                'get_visits_for_dataset': get_visits_for_dataset,
                'get_geonetwork_link': get_geonetwork_link,
                'get_tooltip_content_types': get_tooltip_content_types,
                'unquote_url': unquote_url,
                'scheming_field_only_default_required': scheming_field_only_default_required,
                'add_locale_to_source': add_locale_to_source,
                'scheming_language_text_or_empty': scheming_language_text_or_empty,
                'get_lang_prefix': get_lang_prefix,
                'call_toolkit_function': call_toolkit_function}

    def get_auth_functions(self):
        return {'related_update': auth.related_update,
                'related_create': auth.related_create}

        # IPackageController #

    def after_show(self, context, pkg_dict):
        if u'resources' in pkg_dict and pkg_dict[u'resources']:
            for resource in pkg_dict[u'resources']:
                if 'url_type' in resource and isinstance(resource['url_type'], Missing):
                    resource['url_type'] = None

    def before_index(self, pkg_dict):

        if 'tags' in pkg_dict:
            tags = pkg_dict['tags']
            if tags:
                pkg_dict['tags'] = [tag.lower() for tag in tags]

        if 'vocab_content_type' in pkg_dict:
            content_types = pkg_dict['vocab_content_type']
            if content_types:
                pkg_dict['vocab_content_type'] = [content_type.lower() for content_type in content_types]

        if 'res_format' in pkg_dict:
            res_formats = pkg_dict['res_format']
            if res_formats:
                pkg_dict['res_format'] = [res_format.lower() for res_format in res_formats]

        # Converting from creator_user_id to source. Grouping users default and harvest into harvesters and manual to the rest
        if 'creator_user_id' in pkg_dict:
            user_id = pkg_dict['creator_user_id']
            if user_id:
                user_name = self._get_user_by_id(user_id)
                accepted_harvesters = {'default', 'harvest'}
                if user_name in accepted_harvesters:
                    pkg_dict['source'] = 'External'
                else:
                    pkg_dict['source'] = 'Internal'
        return pkg_dict

    # IActions #
    def get_actions(self):
        return {'package_show': action_package_show}



    # IValidators
    def get_validators(self):
        return {
            'lower_if_exists': validators.lower_if_exists,
            'upper_if_exists': validators.upper_if_exists,
            'tag_string_or_tags_required': validators.tag_string_or_tags_required,
            'create_tags': validators.create_tags,
            'create_fluent_tags': validators.create_fluent_tags,
            'set_private_if_not_admin': validators.set_private_if_not_admin,
            'list_to_string': validators.list_to_string,
            'convert_to_list': validators.convert_to_list,
            'tag_list_output': validators.tag_list_output,
            'repeating_text': validators.repeating_text,
            'repeating_text_output': validators.repeating_text_output,
            'only_default_lang_required': validators.only_default_lang_required
        }


class YTPSpatialHarvester(plugins.SingletonPlugin):
    plugins.implements(ISpatialHarvester, inherit=True)

    # ISpatialHarvester

    def get_package_dict(self, context, data_dict):

        package_dict = data_dict['package_dict']

        list_map = {'access_constraints': 'copyright_notice'}

        for source, target in list_map.iteritems():
            for extra in package_dict['extras']:
                if extra['key'] == source:
                    value = json.loads(extra['value'])
                    if len(value):
                        package_dict['extras'].append({
                            'key': target,
                            'value': value[0]
                        })

        value_map = {'contact-email': ['maintainer_email', 'author_email']}

        for source, target in value_map.iteritems():
            for extra in package_dict['extras']:
                if extra['key'] == source and len(extra['value']):
                    for target_key in target:
                        package_dict[target_key] = extra['value']

        map = {'responsible-party': ['maintainer', 'author']}

        harvester_context = {'model': model, 'session': Session, 'user': 'harvest'}
        for source, target in map.iteritems():
            for extra in package_dict['extras']:
                if extra['key'] == source:
                    value = json.loads(extra['value'])
                    if len(value):
                        for target_key in target:
                            package_dict[target_key] = value[0]['name']

                        # find responsible party from orgs
                        try:
                            name = munge_title_to_name(value[0]['name'])
                            group = get_action('organization_show')(harvester_context, {'id': name})
                            package_dict['owner_org'] = group['id']
                        except NotFound:
                            pass

        config_obj = json.loads(data_dict['harvest_object'].source.config)
        license_from_source = config_obj.get("license", None)

        for extra in package_dict['extras']:
            if extra['key'] == 'resource-type' and len(extra['value']):
                    if extra['value'] == 'dataset':
                        value = 'paikkatietoaineisto'
                    elif extra['value'] == 'series':
                        value = 'paikkatietoaineistosarja'
                    elif extra['value'] == 'service':
                        value = 'paikkatietopalvelu'
                        for temp_extra in package_dict['extras']:
                            if temp_extra['key'] == 'collection_type':
                                temp_extra['value'] = 'Interoperability Tools'
                    else:
                        continue

                    package_dict['content_type'] = value
                    flattened = flatten_dict(package_dict)
                    convert_to_tags_string('content_type')(('content_type',), flattened, {}, context)
                    package_dict = unflatten(flattened)

            if license_from_source is None:
                if extra['key'] == 'licence':
                    value = json.loads(extra['value'])
                    if len(value):
                        package_dict['license'] = value
                        urls = []
                        for i in value:
                            urls += re.findall(r'(https?://\S+)', i)
                        if len(urls):
                            if urls[0].endswith('.'):
                                urls[0] = urls[0][:-1]
                            package_dict['extras'].append({
                                "key": 'license_url',
                                'value': urls[0]
                            })
            else:
                package_dict['license_id'] = license_from_source

            if extra['key'] == 'dataset-reference-date' and len(extra['value']):
                value = json.loads(extra['value'])
                for dates in value:
                    if dates.get("type") == "creation":
                        package_dict['extras'].append({
                            "key": 'resource_created',
                            'value': dates.get("value")
                        })
                    elif dates.get("type") == "publication":
                        package_dict['extras'].append({
                            "key": 'resource_published',
                            'value': dates.get("value")
                        })
                    elif dates.get("type") == "revision":
                        package_dict['extras'].append({
                            "key": 'resource_modified',
                            'value': dates.get("value")
                        })

        # topic category for syke

        topic_categories = data_dict['iso_values'].get('topic-category')
        if topic_categories:
            for category in topic_categories:
                category = category[:50] if len(category) > 50 else category
                package_dict['tags'].append({'name': category})

        return package_dict




_config_template = "ckanext.ytp.organizations.%s"
_node_type = 'service_alert'

_default_organization_name = None
_default_organization_title = None


def _get_variable(config, name):
    variable = _config_template % name
    value = config.get(variable)
    if not value:
        raise Exception('YtpOrganizationsPlugin: required configuration variable missing: %s' % (variable))
    return value.decode('unicode_escape')  # CKAN loads ini file as ascii. Parse unicode escapes here.


def _configure(config=None):
    global _default_organization_name, _default_organization_title
    if _default_organization_name and _default_organization_title:
        return
    if not config:
        config = pylons.config
    _default_organization_name = _get_variable(config, "default_organization_name")
    _default_organization_title = _get_variable(config, "default_organization_title")


def _user_has_organization(username):
    user = model.User.get(username)
    if not user:
        raise NotFound("Failed to find user")
    query = model.Session.query(model.Member).filter(model.Member.table_name == 'user').filter(model.Member.table_id == user.id)
    return query.count() > 0


def _create_default_organization(context, organization_name, organization_title):
    values = {'name': organization_name, 'title': organization_title, 'id': organization_name}
    try:
        return plugins.toolkit.get_action('organization_show')(context, values)
    except NotFound:
        return plugins.toolkit.get_action('organization_create')(context, values)


def action_user_create(context, data_dict):
    _configure()

    result = get_original_method('ckan.logic.action.create', 'user_create')(context, data_dict)
    context = create_system_context()
    organization = _create_default_organization(context, _default_organization_name, _default_organization_title)
    plugins.toolkit.get_action('organization_member_create')(context, {"id": organization['id'], "username": result['name'], "role": "editor"})

    return result


def action_organization_show(context, data_dict):
    try:
        result = get_original_method('ckan.logic.action.get', 'organization_show')(context, data_dict)
    except NotAuthorized:
        raise NotFound

    result['display_name'] = extra_translation(result, 'title') or result.get('display_name', None) or result.get('name', None)
    return result


class YtpOrganizationsPlugin(plugins.SingletonPlugin, DefaultOrganizationForm, YtpMainTranslation):
    """ CKAN plugin to change how organizations work """
    plugins.implements(plugins.IGroupForm, inherit=True)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IRoutes, inherit=True)
    plugins.implements(plugins.ITranslation)

    plugins.implements(plugins.IConfigurer, inherit=True)

    # IConfigurer
    def update_config(self, config):
        plugins.toolkit.add_template_directory(config, 'templates')

    _localized_fields = ['title', 'description', 'alternative_name', 'street_address', 'street_address_pobox',
                         'street_address_zip_code', 'street_address_place_of_business', 'street_address_country',
                         'street_address_unofficial_name', 'street_address_building_id', 'street_address_getting_there',
                         'street_address_parking', 'street_address_public_transport', 'street_address_url_public_transport',
                         'homepage']

    def configure(self, config):
        _configure(config)

    def group_title_validator(self, key, data, errors, context):
        """ Validator to prevent duplicate title.
            See ckan.logic.schema
        """
        contect_model = context['model']
        session = context['session']
        group = context.get('group')

        query = session.query(contect_model.Group.title).filter_by(title=data[key])
        if group:
            group_id = group.id
        else:
            group_id = data.get(key[:-1] + ('id',))
        if group_id and group_id is not dictization_functions.missing:
            query = query.filter(contect_model.Group.id != group_id)
        result = query.first()
        if result:
            errors[key].append(_('Group title already exists in database'))

    def is_fallback(self):
        """ See IGroupForm.is_fallback """
        return False

    def group_types(self):
        """ See IGroupForm.group_types """
        return ['organization']

    def form_to_db_schema_options(self, options):
        """ See DefaultGroupForm.form_to_db_schema_options
            Inserts duplicate title validation to schema.
        """
        schema = super(YtpOrganizationsPlugin, self).form_to_db_schema_options(options)
        schema['title'].append(self.group_title_validator)
        return schema

    def form_to_db_schema(self):
        schema = super(YtpOrganizationsPlugin, self).form_to_db_schema()
        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_to_extras = toolkit.get_converter('convert_to_extras')

        # schema for homepages
        # schema.update({'homepages': [ignore_missing, convert_to_list, unicode, convert_to_extras]})
        schema.update({'homepage': [ignore_missing, unicode, convert_to_extras]})

        schema.update({'public_adminstration_organization': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'producer_type': [ignore_missing, unicode, convert_to_extras]})

        # schema for extra org info
        # schema.update({'business_id': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'oid': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'alternative_name': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'valid_from': [ignore_missing, date_validator, convert_to_extras]})
        schema.update({'valid_till': [ignore_missing, date_validator, convert_to_extras]})

        # schema for organisation address
        schema.update({'street_address': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_pobox': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'street_address_zip_code': [ignore_missing, unicode, convert_to_extras]})
        schema.update({'street_address_place_of_business': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_country': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_unofficial_name': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_building_id': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_getting_there': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_parking': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_public_transport': [ignore_missing, unicode, convert_to_extras]})
        # schema.update({'street_address_url_public_transport': [ignore_missing, unicode, convert_to_extras]})

        schema = add_translation_modify_schema(schema)
        schema = add_languages_modify(schema, self._localized_fields)

        return schema

    def db_to_form_schema(self):
        schema = ckan.logic.schema.group_form_schema()
        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_from_extras = toolkit.get_converter('convert_from_extras')

        # add following since they are missing from schema
        schema.update({'num_followers': [ignore_missing]})
        schema.update({'package_count': [ignore_missing]})

        # Schema for homepages
        schema.update({'homepage': [convert_from_extras, ignore_missing]})

        # schema for extra org info
        schema.update({'valid_from': [convert_from_extras, ignore_missing]})
        schema.update({'valid_till': [convert_from_extras, ignore_missing]})

        # schema for organisation address
        schema.update({'street_address': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_zip_code': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_place_of_business': [convert_from_extras, ignore_missing]})

        schema.update({'producer_type': [convert_from_extras, ignore_missing]})
        schema.update({'public_adminstration_organization': [convert_from_extras, ignore_missing]})

        # old schema is used to display old data if it exists
        schema.update({'homepages': [convert_from_extras, from_json_to_object, ignore_missing]})
        schema.update({'business_id': [convert_from_extras, ignore_missing]})
        schema.update({'oid': [convert_from_extras, ignore_missing]})
        schema.update({'alternative_name': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_pobox': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_country': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_unofficial_name': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_building_id': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_getting_there': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_parking': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_public_transport': [convert_from_extras, ignore_missing]})
        schema.update({'street_address_url_public_transport': [convert_from_extras, ignore_missing]})

        schema = add_translation_show_schema(schema)
        schema = add_languages_show(schema, self._localized_fields)

        return schema

    def db_to_form_schema_options(self, options):
        if not options.get('api', False):
            return self.db_to_form_schema()
        schema = ckan.logic.schema.group_form_schema()

        return schema

    # From ckanext-hierarchy
    def setup_template_variables(self, context, data_dict):
        from pylons import tmpl_context
        model = context['model']
        group_id = data_dict.get('id')

        if group_id:
            group = model.Group.get(group_id)
            tmpl_context.allowable_parent_groups = \
                group.groups_allowed_to_be_its_parent(type='organization')
        else:
            tmpl_context.allowable_parent_groups = model.Group.all(group_type='organization')

    def _get_dropdown_menu_contents(self, vocabulary_names):
        """ Gets vocabularies by name and mangles them to match data structure required by form.select """

        try:
            user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})
            context = {'user': user['name']}
            menu_items = []

            for vocabulary_name in vocabulary_names:
                vocabulary = toolkit.get_action('vocabulary_show')(context, {'id': vocabulary_name})
                tags = vocabulary.get('tags')

                for tag in sorted(tags):
                    menu_items.append({'value': tag['name'], 'text': tag['display_name']})
            return menu_items
        except:
            return []

    def _get_authorized_parents(self):
        """ Returns a list of organizations under which the current user can put child organizations.

        The user is required to be an admin in the parent. If the user is a sysadmin, then the user will see all allowable parent organizations. """

        if not c.userobj.sysadmin:
            # If the user is not a sysadmin, then show only those parent organizations in which the user is an admin
            admin_in_orgs = model.Session.query(model.Member).filter(model.Member.state == 'active').filter(model.Member.table_name == 'user') \
                .filter(model.Member.capacity == 'admin').filter(model.Member.table_id == c.userobj.id)

            admin_groups = []
            for admin_org in admin_in_orgs:
                if any(admin_org.group.name == non_looping_org.name for non_looping_org in c.allowable_parent_groups):
                    admin_groups.append(admin_org.group)
        else:
            # If the user is a sysadmin, then show all allowable parent organizations
            admin_groups = []
            for group in c.allowable_parent_groups:
                admin_groups.append(group)

        return admin_groups

    def _get_parent_organization_display_name(self, organization_id):
        group = [group for group in c.allowable_parent_groups if group.id == organization_id]
        if group:
            return group[0].title if group[0].title else group[0].id
        return "not_found"

    def _is_organization_in_authorized_parents(self, organization_id, parents):
        group = [group for group in parents if group.name == organization_id]
        if group:
            return True
        return False

    def get_helpers(self):
        return {'get_dropdown_menu_contents': self._get_dropdown_menu_contents,
                'get_authorized_parents': self._get_authorized_parents,
                'get_parent_organization_display_name': self._get_parent_organization_display_name,
                'is_organization_in_authorized_parents': self._is_organization_in_authorized_parents
                }

    def get_auth_functions(self):
        return {'organization_create': auth.organization_create, 'organization_update': auth.organization_update,
                'organization_public_adminstration_change': auth.organization_public_adminstration_change}

    def get_actions(self):
        return {'user_create': action_user_create, 'organization_show': action_organization_show}

    def before_map(self, map):
        organization_controller = 'ckanext.ytp.controller:YtpOrganizationController'

        with SubMapper(map, controller=organization_controller) as m:
            m.connect('organization_members', '/organization/members/{id}', action='members', ckan_icon='group')
            m.connect('/user_list', action='user_list', ckan_icon='user')
            m.connect('/admin_list', action='admin_list', ckan_icon='user')

        map.connect('/organization/new', action='new', controller='organization')
        map.connect('organization_read', '/organization/{id}', controller=organization_controller, action='read', ckan_icon='group')
        map.connect('organization_embed', '/organization/{id}/embed', controller=organization_controller, action='embed', ckan_icon='group')
        return map


def convert_to_list(key, data):
    if isinstance(key, basestring):
        key = [key]
    return key


def convert_from_db_to_form_list(key, data):
    key = unicode(key)
    key = ast.literal_eval(key)
    for i, value in enumerate(key):
        key[i] = unicode(value)

    return key


def from_json_to_object(key, data):
    if not key:
        return key
    key = ast.literal_eval(key)
    if isinstance(key, list):
        for i, value in enumerate(key):
            try:
                parsed = json.loads(value)
                key[i] = parsed
            except:
                pass

    return key


def date_validator(value, context):
    """ Validator for date fields """
    if isinstance(value, datetime.date):
        return value
    if value == '':
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise Invalid(_('Date format incorrect'))

class YtpReportPlugin(plugins.SingletonPlugin, YtpMainTranslation):
    plugins.implements(IReport)
    plugins.implements(plugins.IConfigurer, inherit=True)
    plugins.implements(plugins.ITranslation)

    # IReport

    def register_reports(self):
        import reports
        return [reports.test_report_info, reports.administrative_branch_summary_report_info]

    def update_config(self, config):
        from ckan.plugins import toolkit
        toolkit.add_template_directory(config, 'templates')


def set_to_value(preset_value):
    def method(value, context):
        return preset_value
    return method


def static_value(preset_value):
    def method(value, context):
        return preset_value
    return method


def service_charge_validator(key, data, errors, context):
    """Validates the fields related to service charge.

    If the service has a charge, then the user must also supply either the pricing information URL or a description of the service pricing or both."""

    # Get the value for the service charge radio field
    service_charge_value = data.get(key)

    if service_charge_value is missing or service_charge_value is None or service_charge_value == '':
        # At least one of the service charge values must be selected
        raise Invalid(_('Service charge must be supplied'))
    elif service_charge_value == 'yes':
        # Check if the service has a charge
        # Get the pricing information url and service price description values from the data (the key is a tuple)
        pricing_url_value = data.get(('pricing_information_url',))
        service_price_value = data.get(('service_price_description',))

        if ((pricing_url_value is missing or pricing_url_value is None or pricing_url_value == '') and
                (service_price_value is missing or service_price_value is None or service_price_value == '')):
            # If both the pricing information url and the service price description fields are empty, show an error message
            raise Invalid(_('If there is a service charge, you must supply either the pricing information web address for this service or a description of ' +
                            'the service pricing or both'))
    return service_charge_value


def target_groups_validator(key, data, errors, context):
    """Validates the target groups field.

    At least one of the main target groups needs to be selected."""

    target_groups_value = data.get(key)
    if target_groups_value is missing or target_groups_value is None or target_groups_value == '':
        raise Invalid(_('At least one of the main target groups must to be selected'))
    return target_groups_value


class YTPServiceForm(plugins.SingletonPlugin, toolkit.DefaultDatasetForm):
    plugins.implements(plugins.IDatasetForm, inherit=True)
    plugins.implements(plugins.IConfigurer, inherit=True)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.ITemplateHelpers)

    _localized_fields = ['title', 'notes', 'alternative_title', 'usage_requirements',  # 1
                         'service_provider_other', 'service_class',  # 2
                         'pricing_information_url', 'service_price_description', 'processing_time_estimate',  # 3
                         'service_main_usage', 'decisions_and_documents_electronic_where', 'communicate_service_digitally_how']  # 3

    # optional text fields
    _text_fields = ['alternative_title', 'usage_requirements',  # 1
                    'service_provider_other', 'service_class',  # 2
                    'processing_time_estimate',  # 3
                    'service_main_usage', 'average_service_time_estimate', 'remote_service_duration_per_customer',
                    'decisions_and_documents_electronic_where', 'communicate_service_digitally_how']  # 3
    _radio_fields = ['service_region',  # 1
                     'remote_service', 'decisions_and_documents_electronic',  # 3
                     'communicate_service_digitally']  # 3
    _select_fields = ['service_cluster', 'production_type']  # 1

    _custom_text_fields = _text_fields + _radio_fields + _select_fields

    def update_config(self, config):
        toolkit.add_public_directory(config, '/var/www/resources')
        toolkit.add_resource('public/javascript/', 'ytp_service_js')
        toolkit.add_template_directory(config, 'templates')

        toolkit.add_resource('public/javascript/', 'ytp_common_js')
        toolkit.add_template_directory(config, '../common/templates')

    # IDatasetForm #

    def _modify_package_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_to_extras = toolkit.get_converter('convert_to_extras')

        schema = add_translation_modify_schema(schema)
        schema = add_languages_modify(schema, self._localized_fields)

        for text_field in self._custom_text_fields:
            schema.update({text_field: [ignore_missing, unicode, convert_to_extras]})

        schema.update({'collection_type': [set_to_value(u'Public Service'), unicode, convert_to_extras]})
        schema.update({'extra_information': [ignore_missing, is_url, to_list_json, convert_to_extras]})
        schema.update({'municipalities': [ignore_missing, convert_to_tags_string('municipalities')]})
        schema.update({'target_groups': [target_groups_validator, convert_to_tags_string('target_groups')]})
        schema.update({'life_situations': [ignore_missing, convert_to_tags_string('life_situations')]})

        # Make the following fields mandatory
        schema.update({'decisions_and_documents_electronic': [unicode, convert_to_extras]})
        schema.update({'communicate_service_digitally': [unicode, convert_to_extras]})

        # Apply the service_charge_validator to the service charge field
        schema.update({'service_charge': [service_charge_validator, unicode, convert_to_extras]})
        schema.update({'pricing_information_url': [is_url, unicode, convert_to_extras]})
        schema.update({'service_price_description': [unicode, convert_to_extras]})

        # Service channels
        resources_schema = schema.get('resources')
        resources_schema.update({'url': [ignore_missing, unicode]})

        # Remove tags from the form's data model
        del schema['tag_string']

        return schema

    def create_package_schema(self):
        schema = super(YTPServiceForm, self).create_package_schema()
        return self._modify_package_schema(schema)

    def update_package_schema(self):
        schema = super(YTPServiceForm, self).update_package_schema()
        return self._modify_package_schema(schema)

    def show_package_schema(self):
        schema = super(YTPServiceForm, self).show_package_schema()

        ignore_missing = toolkit.get_validator('ignore_missing')
        convert_from_extras = toolkit.get_converter('convert_from_extras')

        schema = add_translation_show_schema(schema)
        schema = add_languages_show(schema, self._localized_fields)

        for text_field in self._custom_text_fields:
            schema.update({text_field: [convert_from_extras, ignore_missing]})

        schema['tags']['__extras'].append(toolkit.get_converter('free_tags_only'))
        schema.update({'collection_type': [static_value(u'Public Service')]})
        schema.update({'municipalities': [toolkit.get_converter('convert_from_tags')('municipalities'), string_join, ignore_missing]})
        schema.update({'target_groups': [toolkit.get_converter('convert_from_tags')('target_groups'), string_join, ignore_missing]})
        schema.update({'life_situations': [toolkit.get_converter('convert_from_tags')('life_situations'), string_join, ignore_missing]})

        schema.update({'service_charge': [convert_from_extras, ignore_missing]})
        schema.update({'pricing_information_url': [convert_from_extras, ignore_missing]})
        schema.update({'service_price_description': [convert_from_extras, ignore_missing]})

        # Do not show the tags
        del schema['tag_string']

        return schema

    def package_types(self):
        return ['service']

    def is_fallback(self):
        return False

    def new_template(self):
        return 'package/ytp/service/new.html'

    def package_form(self):
        return 'package/ytp/service/new_package_form.html'

    def setup_template_variables(self, context, data_dict):
        c.preselected_group = request.params.get('group', None)
        super(YTPServiceForm, self).setup_template_variables(context, data_dict)

    # # IAuthFunctions # #

    def _package_common(self, context, data_dict=None):
        if data_dict is None:
            data_dict = {}

        if data_dict and (data_dict.get('type', None) == 'service' or data_dict.get('collection_type', None) == u'Public Service'):
            result = self._can_create_service(context, data_dict)
            if result.get('success') is False:
                return result
            owner_organization = data_dict.get('owner_org', None)
            if owner_organization:
                organization = model.Group.get(owner_organization)
                if not organization:
                    return {'success': False, 'msg': _('Organization does not exist')}
                if organization.extras.get('public_adminstration_organization', None) != 'true':
                    return {'success': False, 'msg': _('Invalid organization type')}
        return None

    def _package_create(self, context, data_dict=None):
        result = self._package_common(context, data_dict)
        if result:
            return result

        return tools.get_original_method('ckan.logic.auth.create', 'package_create')(context, data_dict)

    def _package_update(self, context, data_dict=None):
        result = self._package_common(context, data_dict)
        if result:
            return result

        package = ckan_auth.get_package_object(context, data_dict)
        harvest_object_count = model.Session.query(HarvestObject) \
            .filter(HarvestObject.package_id == package.id) \
            .filter(HarvestObject.current == True) \
            .count()  # noqa

        if harvest_object_count > 0:
            return {'success': False, 'msg': _("Harvested datasets are read-only")}

        return tools.get_original_method('ckan.logic.auth.update', 'package_update')(context, data_dict)

    def _can_create_service(self, context, data_dict=None):
        log.debug("Can create service")
        if 'auth_user_obj' not in context:
            return {'success': False, 'msg': _("Login required")}
        user_object = context['auth_user_obj']
        query = model.Session.query(model.Member).filter(model.Member.table_name == "user").filter(model.Member.table_id == user_object.id) \
            .filter(model.Member.state == 'active').filter(or_(model.Member.capacity == 'admin', model.Member.capacity == 'editor'))
        if query.count() < 1:
            return {'success': False, 'msg': _('User %s is not part of any public organization')}

        group_ids = [member.group_id for member in query]

        for group in model.Session.query(model.Group).filter(model.Group.id.in_(group_ids)):
            if 'public_adminstration_organization' in group.extras and group.extras['public_adminstration_organization'] == 'true':
                return {'success': True}

        return {'success': False, 'msg': _('User %s is not part of any public organization')}

    def get_auth_functions(self):
        return {'package_create': self._package_create, 'package_update': self._package_update, 'can_create_service': self._can_create_service}

    # # ITemplateHelpers # #

    def _service_organizations(self):
        ''' modified from organization_list_for_user '''
        context = {'user': c.user}
        data_dict = {'permission': 'create_dataset'}
        user = context['user']

        toolkit.check_access('organization_list_for_user', context, data_dict)
        sysadmin = authz.is_sysadmin(user)

        orgs_q = model.Session.query(model.Group) \
            .filter(model.Group.is_organization == True) \
            .filter(model.Group.state == 'active')  # noqa

        if not sysadmin:
            # for non-Sysadmins check they have the required permission

            permission = data_dict.get('permission', 'edit_group')

            roles = authz.get_roles_with_permission(permission)

            if not roles:
                return []
            user_id = authz.get_user_id_for_username(user, allow_none=True)
            if not user_id:
                return []

            q = model.Session.query(model.Member) \
                .filter(model.Member.table_name == 'user') \
                .filter(model.Member.capacity.in_(roles)) \
                .filter(model.Member.table_id == user_id) \
                .filter(model.Member.state == 'active')

            group_ids = []
            for row in q.all():
                group_ids.append(row.group_id)

            if not group_ids:
                return []

            orgs_q = orgs_q.filter(model.Group.id.in_(group_ids))
            orgs_q = orgs_q.join(model.GroupExtra).filter(model.GroupExtra.key == u'public_adminstration_organization') \
                .filter(model.GroupExtra.value == u'true')  # YTP modification

        return model_dictize.group_list_dictize(orgs_q.all(), context)

    def get_helpers(self):
        return {'service_organization': self._service_organizations,
                'get_dict_tree_from_json': get_dict_tree_from_json}


class YtpThemePlugin(plugins.SingletonPlugin, YtpMainTranslation):
    plugins.implements(plugins.IRoutes, inherit=True)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITranslation)

    default_domain = None
    logos = {}

    # TODO: We should use named routes instead
    _manu_map = [(['/user/%(username)s', '/%(language)s/user/%(username)s'], menu.UserMenu, menu.MyInformationMenu),
                 (['/dashboard/organizations', '/%(language)s/dashboard/organizations'], menu.UserMenu, menu.MyOrganizationMenu),
                 (['/dashboard/datasets', '/%(language)s/dashboard/datasets'], menu.UserMenu, menu.MyDatasetsMenu),
                 (['/user/delete-me', '/%(language)s/user/delete-me'], menu.UserMenu, menu.MyCancelMenu),
                 (['/user/edit', '/%(language)s/user/edit', '/user/edit/%(username)s', '/%(language)s/user/edit/%(username)s'],
                  menu.UserMenu, menu.MyPersonalDataMenu),
                 (['/user/activity/%(username)s', '/%(language)s/user/activity/%(username)s'], menu.UserMenu, menu.MyInformationMenu),
                 (['/user', '/%(language)s/user'], menu.ProducersMenu, menu.ListUsersMenu),
                 (['/%(language)s/organization', '/organization'], menu.ProducersMenu, menu.OrganizationMenu),
                 (['/%(language)s/dataset/new?collection_type=Open+Data', '/dataset/new?collection_type=Open+Data'], menu.PublishMenu, menu.PublishDataMenu),
                 (['/%(language)s/dataset/new?collection_type=Interoperability+Tools', '/dataset/new?collection_type=Interoperability+Tools'],
                  menu.PublishMenu, menu.PublishToolsMenu),
                 (['/%(language)s/service/new', '/service/new'],
                  menu.PublishMenu, menu.PublishServiceMenu),
                 (['/%(language)s/postit/return', '/postit/return'], menu.ProducersMenu, menu.PostitNewMenu),
                 (['/%(language)s/postit/new', '/postit/new'], menu.ProducersMenu, menu.PostitNewMenu)]

    # IRoutes #

    def before_map(self, m):
        """ Redirect data-path in stand-alone environment directly to CKAN. """
        m.redirect('/data/*(url)', '/{url}', _redirect_code='301 Moved Permanently')

        controller = 'ckanext.ytp.controller:YtpThemeController'
        m.connect('/postit/new', controller=controller, action='new_template')
        m.connect('/postit/return', controller=controller, action='return_template')

        return m

    # IConfigurer #

    def update_config(self, config):
        toolkit.add_template_directory(config, 'templates')
        toolkit.add_template_directory(config, '/var/www/resources/templates')
        toolkit.add_public_directory(config, '/var/www/resources')
        toolkit.add_resource('/var/www/resources', 'ytp_resources')
        toolkit.add_public_directory(config, 'public')
        toolkit.add_resource('public/javascript', 'theme_javascript')
        toolkit.add_template_directory(config, 'postit')

    # IConfigurable #

    def configure(self, config):
        self.default_domain = config.get("ckanext.ytp.default_domain")
        logos = config.get("ckanext.ytp.theme.logos")
        if logos:
            self.logos = dict(item.split(":") for item in re.split("\s+", logos.strip()))

    # ITemplateHelpers #

    def _short_domain(self, hostname, default=None):
        if not hostname or hostname[0].isdigit():
            return default or self.default_domain or ""
        return '.'.join(hostname.split('.')[-2:])

    def _get_menu_tree(self, current_url, language):
        parsed_url = urlparse.urlparse(current_url)
        for patterns, handler, selected in self._manu_map:
            for pattern in patterns:
                if type(pattern) in types.StringTypes:
                    values = {'language': language}
                    if c.user:
                        values['username'] = c.user
                    try:
                        pattern_url = urlparse.urlparse(pattern % values)

                        if parsed_url.path == pattern_url.path:
                            skip = False
                            if pattern_url.query:
                                parsed_parameters = urlparse.parse_qs(parsed_url.query)
                                if not parsed_parameters:
                                    skip = True
                                else:
                                    for key, value in urlparse.parse_qs(pattern_url.query).iteritems():
                                        parameter = parsed_parameters.get(key, None)
                                        if not parameter or parameter[0] != value[0]:
                                            skip = True
                                            break
                            if not skip:
                                return handler(self).select(selected).to_drupal_dictionary()
                    except KeyError:
                        pass  # user not logged in
                elif pattern.match(current_url):
                    return handler(self).select(selected).to_drupal_dictionary()
        return None

    def _get_menu_for_page(self, current_url, language):
        """ Fetches static side menu for url and language. """
        tree = self._get_menu_tree(current_url, language)
        if tree:
            return {'tree': tree}
        else:
            return {}

    def _site_logo(self, hostname, default=None):

        if "avoindata" in hostname:
            hostname = "avoindata"
        elif "opendata" in hostname:
            hostname = "opendata"

        lang = helpers.lang() if helpers.lang() else "default"
        dict_key = hostname + "_" + lang

        logo = self.logos.get(dict_key, self.logos.get('default', None))

        if logo:
            return literal('<img src="%s" class="site-logo" />' % helpers.url_for_static("/images/logo/%s" % logo))
        else:
            return self._short_domain(hostname, default)

    def _drupal_footer(self):
        lang = helpers.lang() if helpers.lang() else "fi"  # Finnish as default language

        try:
            # Call our custom Drupal API to get footer content
            hostname = config.get('ckan.site_url', '')
            response = urllib2.urlopen(hostname + '/api/footer/' + lang)
            return response.read().decode("utf-8")
        except urllib2.HTTPError:
            return ''
        except:
            return ''

        return None

    def get_helpers(self):
        return {'short_domain': self._short_domain, 'get_menu_for_page': self._get_menu_for_page,
                'site_logo': self._site_logo, 'drupal_footer': self._drupal_footer}


def _get_user_image(user):
    image_url = user.extras.get('image_url', None)
    if not image_url:
        return helpers.url_for_static('images/user_placeholder_box.png')
    elif not image_url.startswith('http'):
        return helpers.url_for_static('uploads/user/%s' % image_url, qualified=True)
    return image_url


def _user_image(user, size):
    url = _get_user_image(user) or ""
    return literal('<img src="%s" width="%s" height="%s" class="media-image" />' % (url, size, size))


def helper_is_pseudo(user):
    """ Check if user is pseudo user """
    return user in [model.PSEUDO_USER__LOGGED_IN, model.PSEUDO_USER__VISITOR]


def helper_linked_user(user, maxlength=0, avatar=20):
    """ Return user as HTML item """
    if not isinstance(user, model.User):
        user_name = unicode(user)
        user = model.User.get(user_name)
        if not user:
            return user_name
    if user:
        name = user.name if model.User.VALID_NAME.match(user.name) else user.id
        icon = _user_image(user, avatar)
        displayname = user.display_name
        if maxlength and len(user.display_name) > maxlength:
            displayname = displayname[:maxlength] + '...'
        return icon + u' ' + link_to(displayname,
                                     helpers.url_for(controller='user', action='read', id=name), class_='')


def helper_organizations_for_select():
    organizations = [{'value': organization['id'], 'text': organization['display_name']} for organization in helpers.organizations_available()]
    return [{'value': '', 'text': ''}] + organizations


def helper_main_organization(user=None):
    user = user or c.userobj

    if not user:
        return None

    main_organization = user.extras.get('main_organization', None)

    if main_organization:
        context = {'model': model, 'session': model.Session, 'user': c.user}
        return toolkit.get_action('organization_show')(context, {'id': main_organization})
    else:
        if c.userobj.sysadmin:
            return None  # Admin is part of all organization so main organization would be invalid every time.
        available = helpers.organizations_available()
        return available[0] if available else None


def get_image_upload_size():
    return config.get('ckan.max_image_size', 2)


class YtpUserPlugin(plugins.SingletonPlugin, YtpMainTranslation):
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IRoutes, inherit=True)
    plugins.implements(plugins.ITranslation)

    default_domain = None

    def update_config(self, config):
        toolkit.add_template_directory(config, 'templates')
        toolkit.add_resource('public/javascript/', 'ytp_common_js')
        toolkit.add_public_directory(config, 'public')

    def configure(self, config):
        from ckanext.ytp.model import setup as model_setup
        model_setup()

    def get_helpers(self):
        return {'linked_user': helper_linked_user, 'organizations_for_select': helper_organizations_for_select, 'is_pseudo': helper_is_pseudo,
                'main_organization': helper_main_organization,
                'get_image_upload_size': get_image_upload_size}

    def get_auth_functions(self):
        return {'user_update': logic.auth_user_update, 'user_list': logic.auth_user_list, 'admin_list': logic.auth_admin_list}

    def get_actions(self):
        return {
            'user_update': logic.action_user_update,
            #'user_show': logic.action_user_show,
             'user_list': logic.action_user_list}

    def before_map(self, map):
        # Remap user edit to our user controller
        user_controller = 'ckanext.ytp.controller:YtpUserController'
        with SubMapper(map, controller=user_controller) as m:
            m.connect('/user/edit', action='edit')
            m.connect('/user/edit/{id:.*}', action='edit')
            m.connect('/user/me', action='me')
            #m.connect('/user/{id}', action='read')

        return map
