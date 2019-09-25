import collections
import uuid

import amostra.mongo_client
import ipysheet
from ipysheet import cell
from ipywidgets import link
from traitlets import HasTraits, Int, Unicode, Float

client = amostra.mongo_client.Client(f'mongodb://localhost:27017/test_amostra_ipysheet-{uuid.uuid4()!s}')

samples_sheet = ipysheet.sheet(rows5=5, columns=3, column_headers=['Sample Name', 'Composition', 'UUID'])
for row in range(samples_sheet.rows):
    sample = client.samples.new(name=' ', composition=' ')
    link((cell(row, 0, value=' '), 'value'), (sample, 'name'))
    link((cell(row, 1, value=' '), 'value'), (sample, 'composition'))
    cell(row, 2, value=' ').value = sample.uuid

    
class WorkQueueItem(HasTraits):
    name = Unicode()
    scantime = Float()
    uuid = Unicode()


def search(change):
    '''
    change
    
    {'name': 'value',
     'old': ' ',
     'new': 'a',
     'owner': Cell(column_end=0, column_start=0, row_end=0, row_start=0, type='text', value='a'),
     'type': 'change'}
    '''
    t = change['new']
    c = change['owner']
    update_cell = cell(c.row_start, c.column_end+2)
    for s in client.samples.find({}):
        if t == s.name:
            update_cell.value = s.uuid
            break
    else:
        update_cell.value = ''
        

metadata_sheet = ipysheet.sheet(rows=5, columns=3, column_headers = ['Sample Name', 'ScanTime', 'UUID'])
work_list = collections.deque()
for row in range(metadata_sheet.rows):
    work = WorkQueueItem(name=' ', scantime=0)
    work_list.append(work)
    
    sample_cell = cell(row, 0, value=' ')
    link((sample_cell, 'value'), (work, 'name'))
    sample_cell.observe(search, names = 'value', type='change')
    
    link((cell(row, 1, value=0), 'value'), (work, 'scantime'))
    
    uuid_cell = cell(row, 2, value=' ')
    link((uuid_cell, 'value'), (work, 'uuid'))
