from urllib.parse import quote
from flask import url_for
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS
from bs4 import BeautifulSoup

# Define name spaces
BASE = Namespace('http://www.example.org/test#')
DFD = Namespace('https://w3id.org/dfd/')


def export_dfd(dfd):
    rdf_graph = create_dfd_rdf(dfd)
    turtle = rdf_graph.serialize(format='turtle').decode()
    return turtle


def create_dfd_rdf(dfd):
    # Collect all items in DFD
    dataflow_associations, datastore_associations = collect_item_associations(
        dfd)
    entities, processes, datastores, dataflows = collect_items(
        dfd, dataflow_associations, datastore_associations)
    # Create RDF
    rdf_graph = create_rdf_graph(entities, processes, datastores, dataflows)
    return rdf_graph


def collect_items(hierarchy, dataflow_associations, datastore_associations):
    # Set items records
    entities = set()    # Entity names
    processes = {}      # Process name (key) and parent name or None (value)
    datastores = {}     # Datastore name (key) and associated data (value)
    # Tuples in the form (flow name, source name, target name, associated data)
    dataflows = set()

    # Is sub process
    parent = None if hierarchy['title'] == 'Context diagram' else hierarchy['title']

    # Collect items in graph
    graph = BeautifulSoup(hierarchy['xml_model'], 'lxml')

    for entity in graph.find_all('entity'):
        if not entity.get('from_parent'):
            entities.add(entity.get('label'))

    for process in graph.find_all('process'):
        if not process.get('from_parent'):
            processes[process.get('label')] = parent

    for datastore in graph.find_all('datastore'):
        if not datastore.get('from_parent'):
            label = datastore.get('label')
            associated_data = datastore_associations[label] if label in datastore_associations else None
            datastores[label] = associated_data

    for flow in graph.find_all('mxcell', {"item_type": "flow"}):
        label = flow.get('value')
        source = graph.find(attrs={'id': flow.get('source')}).get('label')
        target = graph.find(attrs={'id': flow.get('target')}).get('label')
        associated_data = dataflow_associations[label] if label in dataflow_associations else None
        dataflows.add((label, source, target, associated_data))

    # Collect items in sub processes and merge them
    for child in hierarchy['children']:
        _, sub_processes, sub_datastores, sub_dataflows = collect_items(
            child, dataflow_associations, datastore_associations)
        processes.update(sub_processes)
        datastores.update(sub_datastores)
        dataflows.update(sub_dataflows)

    return entities, processes, datastores, dataflows


def collect_item_associations(hierarchy):
    # Data flow Name (Key) and Associated Data URI (Value)
    dataflow_associations = {}
    # Data Store Name (Key) and Associated Data URI (Value)
    datastore_associations = {}

    # Find associated data items in graph
    graph = BeautifulSoup(hierarchy['xml_model'], 'lxml')

    for flow in graph.find_all('mxcell', {"item_type": "flow"}):
        label = flow.get('value')
        if flow.get('associated_data'):
            dataflow_associations[label] = flow.get('associated_data')

    for datastore in graph.find_all('datastore'):
        if not datastore.get('from_parent'):
            label = datastore.get('label')
            if datastore.find('mxcell').get('associated_data'):
                datastore_associations[label] = datastore.find(
                    'mxcell').get('associated_data')

    # Collect associated data in sub processes and merge them
    for child in hierarchy['children']:
        sub_dataflow_associations, sub_datastore_associations = collect_item_associations(
            child)
        dataflow_associations.update(sub_dataflow_associations)
        datastore_associations.update(sub_datastore_associations)

    return dataflow_associations, datastore_associations


def create_rdf_graph(entities, processes, datastores, dataflows):
    # Create graph
    graph = Graph()

    # Bind prefix names
    graph.bind('dfd', DFD)

    # Define Entities
    for entity in entities:
        graph.add((BASE[quote(entity)], RDF.type, DFD.Interface))
        graph.add((BASE[quote(entity)], RDFS.label, Literal(entity)))

    # Define Datastores
    for datastore, associated_data in datastores.items():
        graph.add((BASE[quote(datastore)], RDF.type, DFD.DataStore))
        graph.add((BASE[quote(datastore)], RDFS.label, Literal(datastore)))
        if associated_data:
            graph.add((BASE[quote(datastore)],
                       BASE.associatedData, URIRef(associated_data)))

    # Define Processes
    for process, parent in processes.items():
        graph.add((BASE[quote(process)], RDF.type, DFD.Process))
        graph.add((BASE[quote(process)], RDFS.label, Literal(process)))
        if parent:
            graph.add(
                (BASE[quote(process)], DFD.subProcessOf, BASE[quote(parent)]))

    # Define DataFlows
    for i, (label, source, target, associated_data) in enumerate(dataflows):
        graph.add((BASE[f'f{i}'], RDF.type, DFD.DataFlow))
        graph.add((BASE[f'f{i}'], RDFS.label, Literal(label)))
        graph.add((BASE[f'f{i}'], DFD['from'], BASE[quote(source)]))
        graph.add((BASE[f'f{i}'], DFD.to, BASE[quote(target)]))

        if associated_data:
            graph.add((BASE[f'f{i}'], BASE.associatedData,
                       URIRef(associated_data)))

    return graph
