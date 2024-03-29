from bluesky import RunEngine
from ophyd.sim import motor1, motor2, motor
from ophyd import Device, EpicsSignal, Component
from ophyd.signal import EpicsSignalBase
from ophyd.areadetector.filestore_mixins import resource_factory
import databroker
from bluesky.preprocessors import SupplementalData
import os
import uuid
from pathlib import Path
import numpy
from intake import open_catalog
from bluesky_browser.artists.mpl.image import Image
from bluesky_browser.heuristics.image import latest_frame
import functools
from event_model import RunRouter, Filler
from bluesky.run_engine import Dispatcher
from bluesky.utils import CallbackRegistry

class DispatchingFiller(Filler, Dispatcher):
    def __init__(self, handler, inplace):
        super().__init__(handler, inplace=inplace)
        super(Filler, self).__init__()
    def __call__(self, name, doc):
        name, doc = super().__call__(name, doc)  # returns a filled copy
        self.process(name, doc)




# Monkey-patch the databroker instead of using normal config discovery.
databroker.catalog = open_catalog('catalog.yml')
db = databroker.catalog['dmb']()


def handler(resource_path, **kwargs):
    resource_path = resource_path
    
    def get():
        return numpy.load(resource_path)
    return get   


def factory(name, doc):
    def subfactory(name, doc):
        if doc['name'] == 'primary':
            func = functools.partial(latest_frame, image_key='det_img')
            image = Image(func, (480, 640))
            return [image]
        else:
            return []
    return [], [subfactory]




db.filler.handler_registry['npy'] = handler
RE = RunEngine({})
RE.subscribe(db.v1.insert)
dispatching_filler = DispatchingFiller(handler, inplace=False)
dispatching_filler.subscribe(RunRouter([factory]))
#RE.subscribe(dispatching_filler)


# image = self.image_class(func, shape=shape, ax=ax, **self.imshow_options)
# RE.subscribe(RunRouter([factory]))

sd = SupplementalData()
sd.baseline.extend([motor1, motor2, motor])
RE.preprocessors.append(sd)





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


det = Spot('mini:dot', name='det')
