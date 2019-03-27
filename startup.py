# BOILERPLATE SETUP

from bluesky import RunEngine
from bluesky.plans import rel_grid_scan, count
from bluesky.plan_stubs import mv
from event_model import Filler
from ophyd.sim import motor1, motor2, motor
from ophyd import Device, EpicsSignal, Component
from ophyd.signal import EpicsSignalBase
from ophyd.areadetector.filestore_mixins import resource_factory
from databroker import Broker
from bluesky.preprocessors import SupplementalData
import bluesky.plan_stubs as bps
import bluesky.preprocessors
import time
import os
import uuid
from pathlib import Path
import numpy


db = Broker.named('temp')  # WARNING will delete data at the end
RE = RunEngine({})
RE.subscribe(db.insert)
sd = SupplementalData()
RE.preprocessors.append(sd)


def handler(resource_path, **kwargs):
    resource_path = resource_path

    def get():
        return numpy.load(resource_path)

    return get


class ArraySignal(EpicsSignalBase):
    def __init__(self, read_pv, **kwargs):
        super().__init__(read_pv, **kwargs)
        cl = self.cl
        base_pv, _ = read_pv.rsplit(':', maxsplit=1)
        self._size_pv = cl.get_pv(
            ':'.join((base_pv, 'ArraySize_RBV')))

        self._last_ret = None
        self._asset_docs_cache = []

    def trigger(self):
        os.makedirs('/tmp/demo', exist_ok=True)
        st = super().trigger()
        ret = super().read()
        val = ret[self.name]['value'].reshape(self._size_pv.get())

        resource, datum_factory = resource_factory(
            spec='npy',
            root='/tmp',
            resource_path=f'demo/{uuid.uuid4()}.npy',
            resource_kwargs={},
            path_semantics='posix')
        datum = datum_factory({})
        self._asset_docs_cache.append(('resource', resource))
        self._asset_docs_cache.append(('datum', datum))
        fpath = Path(resource['root']) / resource['resource_path']
        numpy.save(fpath, val)

        ret[self.name]['value'] = datum['datum_id']
        self._last_ret = ret
        return st

    def describe(self):
        ret = super().describe()
        ret[self.name]['shape'] = [int(k)
                                   for k in
                                   self._size_pv.get()]
        ret[self.name]['external'] = 'FILESTORE:'
        del ret[self.name]['upper_ctrl_limit']
        del ret[self.name]['lower_ctrl_limit']
        return ret

    def read(self):
        if self._last_ret is None:
            raise Exception('read before being triggered')
        return self._last_ret

    def collect_asset_docs(self):
        items = list(self._asset_docs_cache)
        self._asset_docs_cache.clear()
        for item in items:
            yield item


class Spot(Device):
    img = Component(ArraySignal, ':det')
    roi = Component(EpicsSignal, ':img_sum', kind='hinted')
    exp = Component(EpicsSignal, ':exp', kind='config')
    shutter_open = Component(EpicsSignal, ':shutter_open', kind='config')

    def collect_asset_docs(self):
        yield from self.img.collect_asset_docs()

    def trigger(self):
        return self.img.trigger()


class DarkFrameCache(Device):
    def __init__(self, *args, **kwargs):
        # self.det = det
        self.last_collected = None
        self.just_started = True
        self.update_done = False
        return super().__init__(*args, **kwargs)

    def read(self):
        return self._read

    def read_configuration(self):
        return self._read_configuration

    @property
    def configuration_attrs(self):
        return self._configuration_attrs

    @property
    def read_attrs(self):
        return self._read_attrs

    def describe(self):
        return self._describe

    def describe_configuration(self):
        return self._describe_configuration

    # def describe_configuration(self):
    #     return self.det.describe_configuration

    def collect_asset_docs(self):
        # keep track of when we get restaged to restore these
        yield from self._asset_docs_cache
        self._really_cached = self._asset_docs_cache
        self._asset_docs_cache = []

    def stage(self):
        self._asset_docs_cache = self._really_cached


def teleport(camera, dark_frame_cache):
    dark_frame_cache._describe = camera.describe()
    dark_frame_cache._describe_configuration = camera.describe_configuration()
    dark_frame_cache._read = camera.read()
    dark_frame_cache._read_configuration = camera.read_configuration()
    dark_frame_cache._read_attrs = list(camera.read())
    dark_frame_cache._configuration_attrs = list(camera.read_configuration())
    dark_frame_cache._asset_docs_cache = list(camera.collect_asset_docs())
    dark_frame_cache.last_collected = time.monotonic()


dark_frame_cache = DarkFrameCache(name='dark_frame_cache')


class InsertReferenceToDarkFrame:
    """
    A plan preprocessor that ensures one 'dark' Event per run.
    """
    def __init__(self, dark_frame_cache, stream_name='dark'):
        self.dark_frame_cache = dark_frame_cache
        self.stream_name = stream_name

    def __call__(self, plan):

        def insert_reference_to_dark_frame(msg):
            if msg.command == 'open_run':
                return (
                    bluesky.preprocessors.pchain(
                        bluesky.preprocessors.single_gen(msg),
                        bps.trigger_and_read([self.dark_frame_cache], name='dark')
                    ),
                    None,
                )
            else:
                return None, None

        return (yield from bluesky.preprocessors.plan_mutator(
            plan, insert_reference_to_dark_frame))


def dark_plan(detector, dark_frame_cache, max_age, shutter):
    if (dark_frame_cache.just_started or  # first run after instantiation
        (dark_frame_cache.last_collected is not None and
         time.monotonic() - dark_frame_cache.last_collected > max_age)):
        init_shutter_state = shutter.get()
        yield from bps.mv(shutter, 0)
        yield from bps.trigger(detector, group='cam')
        yield from bps.wait('cam')
        yield from bps.mv(shutter, init_shutter_state)


        teleport(detector, dark_frame_cache)
        dark_frame_cache.just_started = False
        dark_frame_cache.update_done = True
    else:
        dark_frame_cache.update_done = False


class TakeDarkFrames:
    def __init__(self, detector, dark_frame_cache, max_age, shutter):
        self.detector = detector
        self.dark_frame_cache = dark_frame_cache
        self.max_age = max_age
        self.shutter = shutter
        
    def __call__(self, plan):

        def insert_take_dark(msg):
            if msg.command == 'open_run':
                return (
                    bluesky.preprocessors.pchain(
                        dark_plan(
                            self.detector,
                            self.dark_frame_cache,
                            self.max_age,
                            self.shutter),
                        bluesky.preprocessors.single_gen(msg),
                    ),
                    None,
                )
            else:
                return None, None

        return (yield from bluesky.preprocessors.plan_mutator(plan, insert_take_dark))


det = Spot('mini:dot', name='det')
take_dark_frames = TakeDarkFrames(det, dark_frame_cache, 10, det.shutter_open)
insert_reference_to_dark_frame = InsertReferenceToDarkFrame(dark_frame_cache)
RE.preprocessors.append(insert_reference_to_dark_frame)
RE.preprocessors.append(take_dark_frames)

# GENERIC PREPARATION

# Things I always want to write down at the beginning and end of each 'run'.
sd.baseline.extend([motor1, motor2, motor])

# Map human-friendly indexes to actual motor coordinates.
positions = {1: 10.3, 7: 20.1}

# Publish live data stream so that processing.py can get it.
# from bluesky.callbacks.zmq import Publisher
# publisher = Publisher('localhost:5667')
# RE.subscribe(publisher)


os.makedirs('exported', exist_ok=True)
import suitcase.tiff_series
serializer = None
filler = None
dark_descriptor = None
primary_descriptor = None
dark_frame = None


def serialize(name, doc):
    # A hack around the fact that RunRouter isn't ready yet
    global serializer
    global filler
    global dark_descriptor
    global primary_descriptor
    global dark_frame
    if name == 'start':
        filler = Filler({'npy': handler})
        serializer = suitcase.tiff_series.Serializer('exported')
    filler(name, doc)
    if name == 'descriptor' and doc['name'] == 'dark':
        dark_descriptor = doc['uid']
    elif name == 'descriptor' and doc['name'] == 'primary':
        primary_descriptor = doc['uid']
    elif name in ('datum', 'datum_page', 'resource'):
        return
    serializer(name, doc)
    if name == 'event':
        if doc['descriptor'] == dark_descriptor:
            dark_frame = doc['data']['det_img']
        elif doc['descriptor'] == primary_descriptor:
            doc = doc.copy()
            doc['data']['det_img'] = doc['data']['det_img'] = dark_frame
    if name == 'stop':
        serializer.close()


RE.subscribe(serialize)


def multi_sample_count(samples):
    for index, sample_metadata in samples.items():
        yield from mv(motor1, positions[index])
        yield from count([det], md=sample_metadata)


def multi_sample_grid(samples, dx, dy, num_x, num_y):
    uids = []
    for index, sample_metadata in samples.items():
        yield from mv(motor1, positions[index])
        uid = yield from rel_grid_scan(
            [det],
            motor1, -dx, dx, num_x,
            motor2, -dy, dy, num_y, False,  # False -> Do not "snake" path.
            md=sample_metadata)
        uids.append(uid)
    return tuple(uids)  # tuple because immutable is safer

# PREPARATION FOR A SPECIFIC USER/VISIT

# Map human-friendly indexes to sample metadata. (Could be more than just a
# name.) This could be parsed using pandas.read_excel.
# samples = {1: {'composition': 'Ni', 'name': 'S1'},
#            7: {'composition': 'LaB6', 'name': 'S1E'}}

# RE(multi_sample_grid(samples, 1, 1, 3, 3))


# # Never do this...
# def f():
#     for ____:
#         RE(...)
# # because that would break this:
# summarize_plan(f())
