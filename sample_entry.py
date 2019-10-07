import amostra.mongo_client
from ipysheet import cell, sheet
from ipywidgets import link, Layout
import ipywidgets as widgets
from traitlets import HasTraits, Unicode, Float
import time
import uuid


SAMPLE_SHEET_COLUMN_RATIO = [1, 1, 1, 2]
METADATA_SHEET_COLUMN_RATIO = [1, 1, 1, 1, 2]
SAMPLE_LIST = ['CeO2', 'BaTiO3_bulk', 'BaTiO3_nano', 'Aa', 'Bb', 'Cc']
COMPOSITION_LIST = ['Ce O2', 'Ba Ti O3', 'Ba Ti O3', 'A a', 'B b', 'C c']
DESCRIPTION_LIST = ['1mm kapton', ' ', '1mm kapton', ' ', ' ', ' ']
client = amostra.mongo_client.Client(
        f'mongodb://localhost:27017/test_amostra_ipysheet-{uuid.uuid4()!s}')


samples_sheet = sheet(rows=6, columns=4,
                      column_width=SAMPLE_SHEET_COLUMN_RATIO,
                      column_headers=['Sample Name', 'Composition', 'Background', 'UUID'])
# Sample Name    Composition    Scan Time (s)    Grid_X    Grid_Y    Background    user_id
for row in range(samples_sheet.rows):
    sample = client.samples.new(name=' ', composition=' ', description=' ')
    link((cell(row, 0, value=SAMPLE_LIST[row]), 'value'), (sample, 'name'))
    link((cell(row, 1, value=COMPOSITION_LIST[row]), 'value'), (sample, 'composition'))
    link((cell(row, 2, value=DESCRIPTION_LIST[row]), 'value'), (sample, 'description'))
    cell(row, 3, value=' ').value = sample.uuid


class WorkQueueItem(HasTraits):
    name = Unicode()
    scantime = Float()
    gridx = Float(allow_none=True)
    gridy = Float(allow_none=True)
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
    update_cell = metadata_sheet[c.row_start, c.column_end+4]
    for s in client.samples.find({}):
        if n == s.name:
            update_cell.value = s.uuid
            check_list[c.row_start][0] = True
            metadata_sheet[c.row_start, c.column_start].style = {'backgroundColor': 'white'}
            break
    else:
        update_cell.value = ''
        check_list[c.row_start][0] = False
        metadata_sheet[c.row_start, c.column_start].style = {'backgroundColor': 'grey'}


def check(change):
    s = change['new']
    c = change['owner']
    if (isinstance(s, int) or isinstance(s, float)) and s > 0:
        check_list[c.row_start][1] = True
        metadata_sheet[c.row_start, c.column_start].style = {'backgroundColor': 'white'}
    else:
        check_list[c.row_start][1] = False
        metadata_sheet[c.row_start, c.column_start].style = {'backgroundColor': 'grey'}



metadata_sheet = sheet(rows=6, columns=5, column_width=METADATA_SHEET_COLUMN_RATIO,
                       column_headers=['Sample Name', 'ScanTime', 'Grid X', 'Grid Y', 'UUID'])

work_list = [None for i in range(metadata_sheet.rows)]
check_list = [[False, False] for i in range(metadata_sheet.rows)]

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
    # Grid_X cell
    gridx_cell = cell(row, 2, value=0, background_color='white')
    link((gridx_cell, 'value'), (work_list[row], 'gridx'))
    # gridx_cell.observe(check, names='value', type='change')
    # Grid_Y cell
    gridy_cell = cell(row, 3, value=0, background_color='white')
    link((gridy_cell, 'value'), (work_list[row], 'gridy'))
    # gridy_cell.observe(check, names='value', type='change')
    # uuid cell
    uuid_cell = cell(row, 4, value=' ')
    link((uuid_cell, 'value'), (work_list[row], 'uuid'))

log_sheet = sheet(rows=15, columns=5, column_width=METADATA_SHEET_COLUMN_RATIO,
                       column_headers=['Sample Name', 'ScanTime', 'Grid X', 'Grid Y', 'Upload'])
log_sheet.layout.height = '200px'


def on_button_clicked(b):
    for i, e in enumerate(check_list):
        if not any(e):
            first_empty_row = i
            break

    for i in range(4):
        metadata_sheet[first_empty_row, i].value = log_sheet[row_of_button[b], i].value

row_of_button = dict()
for row in range(log_sheet.rows):
    cell(row, 0, value=' ')
    cell(row, 1, value=None)
    cell(row, 2, value=None)
    cell(row, 3, value=None)
    button = widgets.Button(description="Push back")
    button.on_click(on_button_clicked)
    row_of_button[button] = row
    cell(row, 4, button)


from bluesky.plans import count, scan
from bluesky.plan_stubs import mv
from startup import det, motor

# Init current_log_row which is the location of current available line
current_log_row = 0


def plan_factory(work_list):
    for r, w in enumerate(work_list):
        # If all field is legal, run plan
        if all(check_list[r]):
            time.sleep(1)
            for c in range(4):
                metadata_sheet[r, c].style = {'backgroundColor': 'lightblue'}
                metadata_sheet[r, c].read_only = True
                global current_log_row
                current_log_cell = log_sheet[current_log_row,c]
                current_log_cell = cell(current_log_row, c, metadata_sheet[r, c].value)
            print(f'Row {1+r} locked and launch \N{Rocket}')

            current_log_row = current_log_row + 1
            yield from mv(det.exp, w.scantime)
            uid = yield from count([det])
        else:
            print(f'Skip row {1+r}')
    # Reset back to read_only = False

    for r in range(len(work_list)):
        for c in range(4):
            tmp = metadata_sheet[r,c]
            tmp.read_only=False
            if tmp.style['backgroundColor'] == 'lightblue':
                tmp.style = {'backgroundColor': 'white'}


plans = plan_factory(work_list)
