import amostra.mongo_client
from ipysheet import cell, sheet
from ipywidgets import link
from traitlets import HasTraits, Unicode, Float
import uuid


COLUMN_RATIO = [1, 1, 1]

client = amostra.mongo_client.Client(
        f'mongodb://localhost:27017/test_amostra_ipysheet-{uuid.uuid4()!s}')

samples_sheet = sheet(rows=5, columns=3,
                      column_width=COLUMN_RATIO,
                      column_headers=['Sample Name', 'Composition', 'UUID'])
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
     'owner': Cell(column_end=0, column_start=0, row_end=0, row_start=0 ...),
     'type': 'change'}
    '''
    n = change['new']
    c = change['owner']
    update_cell = cell(c.row_start, c.column_end+2)
    for s in client.samples.find({}):
        if n == s.name:
            update_cell.value = s.uuid
            check_list[c.row_start][0] = True
            cell(c.row_start, c.column_start, c.value,
                 background_color='white')
            break
    else:
        update_cell.value = ''
        check_list[c.row_start][0] = False
        cell(c.row_start, c.column_start, c.value, background_color='grey')


def check(change):
    s = change['new']
    c = change['owner']
    if isinstance(s, int) and s > 0:
        check_list[c.row_start][1] = True
        cell(c.row_start, c.column_start, c.value, background_color='white')
    else:
        check_list[c.row_start][1] = False
        cell(c.row_start, c.column_start, c.value, background_color='grey')


metadata_sheet = sheet(rows=5, columns=3, column_width=COLUMN_RATIO,
                       column_headers=['Sample Name', 'ScanTime', 'UUID'])
work_list = [None, None, None, None, None]
check_list = [[False, False],
              [False, False],
              [False, False],
              [False, False],
              [False, False]]
for row in range(metadata_sheet.rows):
    work_list[row] = WorkQueueItem(name=' ', scantime=0)
    # sample cell
    sample_cell = cell(row, 0, value=' ', background_color='grey')
    link((sample_cell, 'value'), (work_list[row], 'name'))
    sample_cell.observe(search, names='value', type='change')
    # scantime cell
    scantime_cell = cell(row, 1, value=0, background_color='grey')
    link((scantime_cell, 'value'), (work_list[row], 'scantime'))
    scantime_cell.observe(check, names='value', type='change')
    # uuid cell
    uuid_cell = cell(row, 2, value=' ')
    link((uuid_cell, 'value'), (work_list[row], 'uuid'))


from bluesky.plans import count
from bluesky.plan_stubs import mv
from startup import det
import time


def plan_factory(work_list):
    for r, w in enumerate(work_list):
        time.sleep(3)
        if all(check_list[r]):
            print(f'Lock row {1+r} and \N{Rocket}')
            for c in range(2):
                tmp = cell(r,c, metadata_sheet[r,c].value, read_only=True)
                #tmp = cell(r,c, '\N{Rocket}', read_only=True)

            yield from mv(det.exp, w.scantime)
            yield from count([det])
        else:
            print(f'Skip row {1+r}')
    # Reset back to read_only = False
    for r in range(len(work_list)):
        for c in range(2):
            tmp = cell(r,c, metadata_sheet[r,c].value, read_only=False)


plans = plan_factory(work_list)