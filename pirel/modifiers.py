import pirel.pcells as pc

import pirel.tools as pt

import phidl.geometry as pg

from phidl.device_layout import Port,CellArray,Device,DeviceReference,Group

from pirel.tools import Point,LayoutDefault,LayoutParamInterface,LayoutPart

import pirel.addOns.standard_parts as ps

import pdb

import pandas as pd

import numpy as np

import warnings, re

from copy import copy,deepcopy

# Classes decorators

def makeScaled(cls):

    ''' Class Decorator that accept normalized parameters for resonator designs.

    Descaling rules:
        IDT gap (d) = IDT gap (n) * pitch
        Bus length (d) = Bus length (n) * pitch
        Etch pit width (d) = Etch pit width (d) * active region width
        Anchor width (d) = Anchor width (n) * active region width
        Anchor length (d) = Anchor length (n) * pitch
        Anchor metal X (d) = Anchor metal X (n) * Anchor width
        Anchor metal Y (d) = Anchor metal Y (n) * Anchor length.

    Parameters
    ----------
    cls : class

        pass class of resonator to be decorated.
        (i.e. Scaled(LFE)(name="normalized LFE")).
    '''

    class Scaled(cls):

        def __init__(self,*args,**kwargs):

            cls.__init__(self,*args,**kwargs)

            self._normalized=False

        def _set_params(self,df):

            self._normalize()

            cls._set_params(self,df)

            self._denormalize()

        def get_params(self):

            self._normalize()

            df=cls.get_params(self)

            self._denormalize()

            return df

        def _normalize(self):

            if self._normalized==True:

                raise ValueError("Already normalized")

            p=self.idt.pitch

            active_area_x=self.idt.active_area.x
            anchor_x=self.anchor.size.x
            anchor_y=self.anchor.size.y

            self.idt.y_offset=self.idt.y_offset/p

            # self.idt.length=self.idt.length/p

            self.bus.size=pt.Point(self.bus.size.x,self.bus.size.y/p)

            self.etchpit.x=self.etchpit.x/active_area_x

            self.anchor.size=pt.Point(
                self.anchor.size.x/active_area_x,
                self.anchor.size.y/p)

            self.anchor.metalized=pt.Point(
                self.anchor.metalized.x/anchor_x,
                self.anchor.metalized.y/anchor_y)

            self._normalized=True

        def _denormalize(self):

            if self._normalized==False:

                raise ValueError("Already denormalized")

            p=self.idt.pitch

            self.idt.y_offset=self.idt.y_offset*p

            self.bus.size=pt.Point(self.bus.size.x,self.bus.size.y*p)

            active_area_x=self.idt.active_area.x

            self.etchpit.x=self.etchpit.x*active_area_x

            self.anchor.size=pt.Point(\
                self.anchor.size.x*active_area_x,\
                self.anchor.size.y*p)

            self.anchor.metalized=pt.Point(
                self.anchor.metalized.x*self.anchor.size.x,
                self.anchor.metalized.y*self.anchor.size.y)

            self._normalized=False

            return self

    Scaled.__name__=" ".join(["Scaled",cls.__name__])

    return Scaled

def addPad(cls, pad=pc.Pad, side='top'):
    ''' Class decorator to add probing pads to existing cells.
        Parameters
        ----------
        cls : pirel.LayoutPart
            design where pads have to be added

        Attributes
        ----------
        pad : pirel.Pad
            pad design for the cell

        side : str ( or iterable of str)
            tag for ports
        The pad design needs a port to attach to the existing cell,
            see help for more info.
        '''

    if isinstance(side,str):

        side=[side]

    class Padded(cls):

        def __init__(self,*args,**kwargs):

            cls.__init__(self,*args,**kwargs)

        def draw(self):

            cell=Device(self.name)

            d_ref=cell.add_ref(cls.draw(self),alias='Device')

            pt._copy_ports(d_ref,cell)

            add_pads(cell,self.pad,side)

            return cell

        @staticmethod
        def get_components():

            supercomp=copy(cls.get_components())

            supercomp.update({"Pad":pad})

            return supercomp

        @property
        def resistance_squares(self):

            r0=super().resistance_squares

            for port in cls.draw(self).get_ports():

                self.pad.port=port

                r0=r0+self.pad.resistance_squares

            return r0

        def _bbox_mod(self,bbox):

            LayoutPart._bbox_mod(self,bbox)

            ll=pt.Point(bbox[0])

            ur=pt.Point(bbox[1])

            if any([_=='top' for _ in side]):

                ur=ur-pt.Point(0,float(self.pad.size+self.pad.distance))

            if any([_=='bottom' for _ in side]):

                ll=ll+pt.Point(0,float(self.pad.size+self.pad.distance))

            return (ll.coord,ur.coord)

    Padded.__name__=" ".join([cls.__name__,"w Pad"])

    return Padded

def addPartialEtch(cls):

    class PartialEtched(cls):

        @staticmethod
        def get_components():

            original_comp=copy(cls.get_components())

            for compname,comp_value in original_comp.items():

                if comp_value==pc.IDT:

                    original_comp[compname]=pc.PartialEtchIDT

                    break

            else:

                raise TypeError(f" no IDT to modify in {cls.__name__}")

            return original_comp

    return PartialEtched

    # PartialEtched.draw=cached(PartialEtched)(PartialEtched.draw)

    adddPartialEtch.__name__=cls.__name__+' w PartialEtching'

def addOnePortProbe(cls,probe=pc.GSGProbe):
    ''' adds a one port probe to existing LayoutClass.

    Parameters:
    -----------
        cls : pt.LayoutPart
            the layout drawn with this LayoutPart needs to have
            a 'bottom' and 'top' port.

        probe: pt.LayoutPart
            currently working only on pc.GSGProbe.
    '''

    class OnePortProbed(cls):
        ''' LayoutPart decorated with a one port probe.

        Parameters:
        -----------
            ground_conn_style : ('straight','side')

            gnd_routing_width: float

            routing_layer: tuple.

        '''

        gnd_routing_width=LayoutParamInterface()

        routing_layer=LayoutParamInterface()

        def __init__(self,*args,**kwargs):

            cls.__init__(self,*args,**kwargs)

            self.gnd_routing_width=100.0

            self.routing_layer=(self.probe.layer,LayoutDefault.layerBottom)

        def draw(self):

            device_cell=cls.draw(self)

            probe_cell=self.probe.draw()

            cell=Device(name=self.name)

            cell.add_ref(device_cell, alias=self.name+"Device")

            probe_ref=cell.add_ref(probe_cell, alias=self.name+"Probe")

            self._move_probe_ref(device_cell,probe_ref)

            try:

                self._setup_routings(device_cell,probe_ref,'straight')

                routing_cell=self._draw_probe_routing()

            except:

                self._setup_routings(device_cell,probe_ref,'side')

                routing_cell=self._draw_probe_routing()

            # _add_default_ground_vias(self,routing_cell)

            cell.add_ref(routing_cell,alias=self.name+"GroundTrace")

            return cell

        def get_params(self):

            t=cls.get_params(self)

            pt.pop_all_dict(t, ["ProbeName"])

            pt.pop_all_dict(t, [k for k in t if re.search('SigTrace',k) ])
            pt.pop_all_dict(t, [k for k in t if re.search('GndLeftTrace',k) ])
            pt.pop_all_dict(t, [k for k in t if re.search('GndRightTrace',k) ])

            return t

        def export_all(self):

            df=super().export_all()
            df["DUTResistance"]=super().resistance_squares
            df["ProbeResistance"]=self.probe_resistance_squares

            return df

        @property
        def resistance_squares(self):

            return super().resistance_squares

        @staticmethod
        def get_components():

            supercomp=copy(cls.get_components())

            if issubclass(probe,pc.GSGProbe):

                supercomp.update({
                    "Probe":probe,
                    "SigTrace":pc.ParasiticAwareMultiRouting,
                    "GndLeftTrace":pc.MultiRouting,
                    "GndRightTrace":pc.MultiRouting,
                    "GndVia":pc.Via})

            else:

                raise ValueError("To be implemented")

            return supercomp

        @property
        def probe_resistance_squares(self):

            return 0

        @property
        def probe_dut_distance(self):

            base_dist=self.idt.probe_distance

            if hasattr(self,'pad'):

                if self.pad.size+self.pad.distance>base_dist.y:

                    return pt.Point(base_dist.x,self.pad.size+self.pad.distance)

                else:

                    return base_dist

            elif hasattr(self.probe,'pad'):

                if self.probe.pad.size+self.probe.pad.distance>base_dist.y:

                    return pt.Point(base_dist.x,self.probe.pad.size+self.probe.pad.distance)

                else:

                    return base_dist

            else:

                return base_dist

        def _move_probe_ref(self,device_ref,probe_ref):

            probe_dut_distance=self.probe_dut_distance

            bottom_ports=pt._find_ports(device_ref,'bottom')

            bottom_center=pt._get_centroid(*[pt.Point(p.midpoint) for p in bottom_ports])

            try:

                probe_port=probe_ref.ports['SigN']

            except:

                probe_port=probe_ref.ports['SigN_1']

            probe_ref.move(
                origin=probe_port.midpoint,
                destination=(bottom_center-probe_dut_distance).coord)

        def _setup_routings(self,device_cell,probe_cell,label):

            bbox=super()._bbox_mod(device_cell.bbox)

            if isinstance(self.probe,pc.GSGProbe):

                for index,groundroute in enumerate([self.gndlefttrace,self.gndrighttrace]):

                    groundroute.layer=self.routing_layer

                    groundroute.clearance=bbox

                    groundroute.trace_width=self.gnd_routing_width

                    if index==0:

                        groundroute.side='left'

                        if label=='straight':

                            groundroute.source=(probe_cell.ports['GroundLXN'],)

                        elif label=='side':

                            groundroute.source=(probe_cell.ports['GroundLXW'],)

                    elif index==1:

                        groundroute.side='right'

                        if label=='straight':

                            groundroute.source=(probe_cell.ports['GroundRXN'],)

                        elif label=='side':

                            groundroute.source=(probe_cell.ports['GroundRXE'],)

                    groundroute.destination=tuple(pt._find_ports(device_cell,'top'))

                #signal routing
                signalroute=self.sigtrace

                bottom_ports=pt._find_ports(device_cell,'bottom')

                signalroute.trace_width=bottom_ports[0].width

                signalroute.layer=self.routing_layer

                signalroute.clearance=bbox

                signalroute.source=(probe_cell.ports['SigN'],)

                signalroute.destination=tuple(bottom_ports)

            elif isinstance(self.probe,pc.GSProbe):

                raise ValueError("OnePortProbed with GSprobe to be implemented ")

            else:

                raise ValueError("OnePortProbed without GSG/GSprobe to be implemented ")

        def _draw_probe_routing(self):

            if isinstance(self.probe,pc.GSGProbe):

                routing_cell=Device()

                routing_cell<<self.gndlefttrace.draw()

                routing_cell<<self.gndrighttrace.draw()

                routing_cell<<self.sigtrace.draw()

                return routing_cell

            else :

                raise ValueError("To be implemented")

    OnePortProbed.__name__=" ".join([cls.__name__,"w Probe"])

    return OnePortProbed

def addLargeGround(probe):

    class LargeGrounded(probe):

        ground_size=LayoutParamInterface()

        def __init__(self,*args,**kwargs):

            probe.__init__(self,*args,**kwargs)

            self.ground_size=LayoutDefault.GSGProbe_LargePadground_size

        def draw(self):

            oldprobe=probe.draw(self)

            cell=pg.deepcopy(oldprobe)

            groundpad=pg.compass(
                size=(self.ground_size,self.ground_size),
                layer=self.layer)

            [_,_,ul,ur,*_]=pt._get_corners(groundpad)

            for alias in cell.aliases:

                if 'GroundLX' in alias:

                    dest=cell[alias].ports['N'].endpoints[1]

                    for portname in cell.ports:

                        if alias in portname:

                            cell.remove(cell.ports[portname])

                    cell.remove(cell[alias])

                    groundref=cell.add_ref(groundpad,alias=alias)

                    groundref.move(origin=ur.coord,\
                    destination=dest)

                    pt._copy_ports(groundref,cell,prefix="GroundLX")

                if 'GroundRX' in alias:

                    dest=cell[alias].ports['N'].endpoints[0]

                    for portname in cell.ports:

                        if alias in portname:

                            cell.remove(cell.ports[portname])

                    cell.remove(cell[alias])

                    groundref=cell.add_ref(groundpad,alias=alias)

                    groundref.move(origin=ul.coord,\
                    destination=dest)

                    for portname in cell[alias].ports:

                        cell.remove(cell[alias].ports[portname])

                    pt._copy_ports(groundref,cell,prefix="GroundRX")

            return cell

    # LargeGnd.draw=pt.cached(LargeGnd)(LargeGnd.draw)

    LargeGrounded.__name__=" ".join([probe.__name__,"w Large Ground"])

    return LargeGrounded

def makeArray(cls,n=2):

    if not isinstance(n,int):

        raise ValueError(" n needs to be integer")

    class Arrayed(cls):

        n_blocks=LayoutParamInterface()

        def __init__(self,*args,**kwargs):

            cls.__init__(self,*args,**kwargs)

            self.n_blocks=n

        def draw(self):

            unit_cell=cls.draw(self)

            port_names=list(unit_cell.ports.keys())

            cell=pt.draw_array(unit_cell,\
                self.n_blocks,1)

            cell.name=self.name

            return cell

        @property
        def resistance_squares(self):

            r=super().resistance_squares

            cell=cls.draw(self)

            for p in cell.get_ports():

                if 'bottom' in p.name:

                    p_bot=p

                    break

            w=p_bot.width

            l=w

            n_blocks=self.n_blocks

            if n_blocks==1:

                return r+l/w

            else:

                x_dist=self.idt.active_area.x+self.etchpit.x*2

                if n_blocks%2==1 :

                    return pt.parallel_res(r+l/w,(r+2*x_dist/l)/(n_blocks-1))

                if n_blocks%2==0 :

                    if n_blocks==2:

                        return (r+x_dist/l)/2

                    else:

                        return pt.parallel_res((r+x_dist/l)/2,(r+2*x_dist/l)/(n_blocks-2))

        def export_all(self):

            df=super().export_all()

            df["SingleDeviceResistance"]=super().resistance_squares

            return df

    Arrayed.__name__= " ".join([f"{n} array of",cls.__name__])

    return Arrayed

def addPassivation(cls,margin=(2,2)):

    class Passivated(cls):

        passivation_margin=LayoutParamInterface()
        passivation_scale=LayoutParamInterface()
        passivation_layer=LayoutParamInterface()

        def __init__(self,*a,**kw):

            cls.__init__(self,*a,**kw)
            self.passivation_margin=LayoutDefault.PassivationMargin
            self.passivation_scale=LayoutDefault.PassivationScale
            self.passivation_layer=LayoutDefault.PassivationLayer

        def draw(self):

            supercell=cls.draw(self)

            cell=pt.Device(self.name)

            master_ref=cell.add_ref(supercell,alias='Device')

            # pt._copy_ports(master_ref,cell)

            rect=pg.rectangle(
                size=(
                    master_ref.size[0]*self.passivation_scale.x,
                    master_ref.size[1]*self.passivation_scale.y))

            rect.move(origin=rect.center,
                destination=master_ref.center)

            pa=pg.boolean(rect,
                pg.bbox(
                    master_ref.bbox+
                    np.array([(-1*self.passivation_margin).coord, self.passivation_margin.coord])),
                    operation='xor')

            for l in self.passivation_layer:

                cell.add_polygon(pa.get_polygons(),layer=(l,0))

            [ll,lr,ul,ul,c,n,s,w,e]=pt._get_corners(cell)

            bottom_port=Port(
                name='S_1',
                width=self.size.x,
                orientation=270,
                midpoint=s.coord)

            top_port=Port(
                name='N_2',
                width=self.size.x,
                orientation=90,
                midpoint=n.coord)

            cell.add_port(top_port)
            cell.add_port(bottom_port)

            cell.add(pt._make_poly_connection(
                bottom_port,
                master_ref.ports['S_1'],
                layer=self.layer))

            cell.add(pt._make_poly_connection(
                top_port,
                master_ref.ports['N_2'],
                layer=self.layer))

            return cell

    Passivated.__name__="Passivated "+cls.__name__

    return Passivated

def makeFixture(cls,style='open'):

    class Fixture(cls):

        style=LayoutParamInterface('short','open')

        def __init__(self,*a,**k):

            super().__init__(*a,**k)

            self.style=style

        def draw(self):

            supercell=cls.draw(self)

            cell=pg.deepcopy(supercell)

            style=self.style

            if style=='open':

                pt._remove_alias(cell,'IDT')

            if style=='short':

                idt_cells=pt._find_alias(cell,'IDT')

                for idt_cell in idt_cells:

                    s=pt._make_poly_connection(idt_cell.ports['top'],idt_cell.ports['bottom'],self.idt.layer)

                    cell<<s

                pt._remove_alias(cell,'IDT')

            return cell

        @property
        def resistance_squares(self):

            style=self.style

            if style=='open':

                from numpy import Inf
                return 1e9

            elif style=='short':

                cell=cls.draw(self)

                ports=cell.get_ports()

                top_port=cell.ports['top']
                bottom_port=cell.ports['bottom']

                l=top_port.y-bottom_port.y
                w=(top_port.width+bottom_port.width)/2

                return l/w

    Fixture.__name__=f"fixture for {cls.__name__}"

    return Fixture

def makeNpaths(cls, pad=pc.Pad, n=4):

    if not isinstance(n,int):

        raise ValueError(f"n needs to be integer, {n.__class__.__name__} was passed")

    if not issubclass(pad,LayoutPart):

        raise ValueError(f"pad needs to be a LayoutPart, {pad.__class__.__name__} was passed")

    class NpathsOf(cls):

        n_copies=LayoutParamInterface()

        spacing=LayoutParamInterface()

        comm_pad_length=LayoutParamInterface()

        def __init__(self,*a,**k):

            cls.__init__(self,*a,**k)

            self.n_copies=n

            self.spacing=LayoutDefault.NPathSpacing

            self.comm_pad_length=LayoutDefault.NPathCommLength

            NpathsOf._set_relations(self)

        def draw(self):

            NpathsOf._set_relations(self)

            cell=pg.deepcopy(cls.draw(self))

            connect_ports(
                cell,
                conn_dist=self.idt.probe_distance,
                tags='top',
                layers=self.pad.layer)

            add_pads(cell,self.pad,tags='top')

            out_cell=pg.Device(self.name)

            refs=[]

            for n in range(1,self.n_copies+1):

                refs.append(out_cell.add_ref(cell,alias='Device'+str(n)))

                origin=pt.Point(refs[-1].xmin,refs[-1].ymin)

                transl=pt.Point(n*refs[-1].xsize,0)+n*self.spacing

                refs[-1].move(destination=transl.coord)

                if n%2==0 and n>0:

                    refs[-1].rotate(
                        angle=180,
                        center=(refs[-1].center[0],refs[-1].ymin))

                    refs[-1].move(destination=(0,-self.comm_pad_length))

            comm_pad=Device()

            for l in self.pad.layer:

                comm_pad<<pg.rectangle(size=(out_cell.xsize,self.comm_pad_length),layer=l)

            add_vias(comm_pad,comm_pad.bbox,self.via,self.via.size*2)

            comm_pad.move(origin=(comm_pad.xmin,comm_pad.ymin),
                         destination=(out_cell.xmin,out_cell.ymin+(out_cell.ysize-self.comm_pad_length)/2))

            out_cell.add_ref(comm_pad,alias='CommPad')

            return out_cell

        @staticmethod
        def get_components():

            pars=copy(cls.get_components())

            pars.update({
            # "TestDevice":OnePortProbed(cls,probe),
            "Pad":pad,"Via":pc.Via})

            return pars

        def get_params(self):

            pars=copy(cls.get_params(self))

            tbr=[]

            for name in pars:

                if "TestDevice" in name:

                    if not "GndRoutingWidth" in name:

                        tbr.append(name)

                if "PadDistance" in name:

                    tbr.append(name)

            pt.pop_all_dict(pars,tbr)

            return pars

        def _set_relations(self):

            try:

                cls._set_relations(self)

            except:

                pass

            self.pad.distance=0

    NpathsOf.__name__=" ".join([f"{n} paths of",cls.__name__])

    return NpathsOf

def makeSMDCoupledFilter(cls,smd=pc.SMD):

    class SMDCoupledFilterOf(cls):

        order=LayoutParamInterface()

        spacing=LayoutParamInterface()

        def __init__(self,*a,**kw):

            cls.__init__(self,*a,**kw)

            self.order=3

            self.spacing=pt.Point(0,100)

        def draw(self):

            cell=Device(self.name)

            unit_cell=self._draw_unit_cell()

            cell_size=pt.Point(unit_cell.size+self.spacing.coord)

            for n in range(self.order):

                if n>0:

                    top_previous=ref.ports['top']

                ref=cell.add_ref(unit_cell,alias='n_'+str(n))

                ref.move(destination=(cell_size.x,cell_size.y*n))

                if n==0:

                    cell.add_port(ref.ports['bottom'])

                    cell.ports['bottom'].orientation=270

                if n==self.order-1:

                    cell.add_port(ref.ports['top'])

                if n>0:

                    this_bottom=ref.ports['bottom']

                    cell.add(pt._make_poly_connection(top_previous,this_bottom,self.smd.layer))

                for p in pt._find_ports(ref,'Ground'):

                    cell.add_port(port=p,name=p.name+'_'+str(n))

            return cell

        def _draw_unit_cell(self):

            base_device=cls.draw(self)

            unit_cell=Device("FilterUnitCell")

            device_ref=unit_cell.add_ref(base_device,alias="Device")

            smd_ref=unit_cell.add_ref(self.smd.draw(),alias='Coupler')

            smd_ref.move(origin=(smd_ref.x,smd_ref.ymin),
                destination=(device_ref.x,device_ref.ymax))

            smd_ref.move(destination=self.spacing.coord)

            for p in pt._find_ports(device_ref,tag='bottom'):

                unit_cell.add_port(p)

            for p in pt._find_ports(device_ref,tag='Ground'):

                unit_cell.add_port(p)

            unit_cell.add_port(port=smd_ref.ports["N_2"],name='top')

            unit_cell<<self._draw_unit_cell_routing(unit_cell)

            self._add_ground_extensions(unit_cell)

            return unit_cell

        def _draw_unit_cell_routing(self,unit_cell):

            r=pc.MultiRouting()

            r.layer=self.smd.layer

            r.source=tuple(pt._find_ports(unit_cell["Device"],'top'))

            r.destination=(unit_cell["Coupler"].ports["S_1"],)

            r.set_auto_overhang(True)

            conn=r.draw()

            conn.flatten()

            return conn

        def _add_ground_extensions(self,cell):

            ext_width=abs(cell.xmin-cell["Device"].parent.ports["GroundLX"].midpoint[0])

            for p in pt._find_ports(cell,'Ground'):

                p_norm=Point(p.normal[1])-Point(p.normal[0])

                p_ext=Port(
                    name=p.name,
                    orientation=p.orientation,
                    width=p.width,
                    midpoint=(pt.Point(p.midpoint)+p_norm*ext_width).coord)

                conn_cell=pt._make_poly_connection(p,p_ext,(self.idt.layer,self.plate_layer))

                _add_default_ground_vias(self,conn_cell)

                cell.add(conn_cell)

                cell.ports.pop(p.name)

                cell.add_port(p_ext)

        @staticmethod
        def get_components():

            pars=copy(cls.get_components())

            pars.update({"SMD":smd})

            return pars

    SMDCoupledFilterOf.__name__=" ".join(["SMD coupled filter of",cls.__name__])

    return SMDCoupledFilterOf

def makeTwoPortProbe(cls):

    class TwoPort(cls):

        offset=LayoutParamInterface()

        def __init__(self,*a,**kw):

            if not issubclass(cls,(pc.GSGProbe,pc.GSProbe)):

                raise TypeError(f"passed probe class is invalid ({cls.__name__})")

            cls.__init__(self,*a,*kw)

            self.offset=LayoutDefault.TwoPortProbeoffset

        def draw(self):

            def mirror_label(str):

                if 'N_' in str:

                    return str.replace('N_','S_')

                if 'E_' in str:

                    return str.replace('E_','W_')

                if 'S_' in str:

                    return str.replace('S_','N_')

                if 'W_' in str:

                    return str.replace('W_','E_')

                return str

            cell=Device(name=self.name)

            probe_cell=super().draw()

            p1=cell.add_ref(probe_cell,alias='Port1')

            p2=cell.add_ref(probe_cell,alias='Port2')

            p2.rotate(
                center=(p1.x,p1.ymax),
                angle=180)

            p2.move(destination=self.offset.coord)

            for n,p in p1.ports.items():

                cell.add_port(port=p,name=n+'_1')

            for n,p in p2.ports.items():

                if 'LX' in n:

                    cell.add_port(port=p,name=mirror_label(n+'_2').replace('LX','RX'))

                else:

                    if 'RX' in n:

                        cell.add_port(port=p,name=mirror_label(n+'_2').replace('RX','LX'))

                    else:

                        cell.add_port(port=p,name=mirror_label(n+'_2'))

            return cell

    TwoPort.__name__=f"Two Port {cls.__name__}"

    return TwoPort

def addTwoPortProbe(cls,probe=makeTwoPortProbe(pc.GSGProbe)):

    class TwoPortProbed(addOnePortProbe(cls,probe)):

        def __init__(self,*a,**kw):

            super().__init__(*a,**kw)

        def draw(self):

            device_cell=cls.draw(self)

            cell=Device(name=self.name)

            device_ref=cell.add_ref(device_cell, alias="DUT")

            self._setup_probe(device_ref)

            probe_cell=self.probe.draw()

            probe_ref=cell.add_ref(probe_cell, alias="Probe")

            self._move_probe_ref(device_ref,probe_ref)

            try:

                self._setup_routings(device_ref,probe_ref,'straight')

                routing_cell=self._draw_probe_routing()

            except:

                    self._setup_routings(device_ref,probe_ref,'side')

                    routing_cell=self._draw_probe_routing()

            try:

                routing_cell.add(self._draw_device_grounds(device_ref,probe_ref,'straight'))

            except:

                routing_cell.add(self._draw_device_grounds(device_ref,probe_ref,'side'))

            # _add_default_ground_vias(self,routing_cell)

            cell.add_ref(routing_cell,alias="GroundTrace")

            return cell

        def _setup_probe(self,device_cell):

            top_ports=[pt.Point(p.midpoint) for p in pt._find_ports(device_cell,'top')]

            bottom_ports=[pt.Point(p.midpoint) for p in pt._find_ports(device_cell,'bottom')]

            top_port_midpoint=pt._get_centroid(*top_ports)

            bottom_port_midpoint=pt._get_centroid(*bottom_ports)

            self.probe.offset=pt.Point(
                (top_port_midpoint.x-bottom_port_midpoint.x),
                (top_port_midpoint.y-bottom_port_midpoint.y)+
                2*self.probe_dut_distance.y)

        def _draw_probe_routing(self):

            if isinstance(self.probe,pc.GSGProbe):

                routing_cell=Device()

                routing_cell<<self.gndlefttrace.draw()

                routing_cell<<self.gndrighttrace.draw()

                routing_cell<<self.sig1trace.draw()

                routing_cell<<self.sig2trace.draw()

                return routing_cell

            else :

                raise ValueError("To be implemented")

        def _setup_routings(self,device_cell,probe_cell,label):

            bbox=super()._bbox_mod(device_cell.bbox)

            if isinstance(self.probe,pc.GSGProbe):

                #ground routing setup
                for index,groundroute in enumerate([self.gndlefttrace,self.gndrighttrace]):

                    groundroute.layer=self.routing_layer

                    groundroute.clearance=bbox

                    groundroute.trace_width=self.gnd_routing_width

                    if index==0:

                        groundroute.side='left'

                        if label=='straight':

                            groundroute.source=(probe_cell.ports['GroundLXN_1'],)

                            groundroute.destination=(probe_cell.ports['GroundLXS_2'],)

                        elif label=='side':

                            groundroute.source=(probe_cell.ports['GroundLXW_1'],)

                            groundroute.destination=(probe_cell.ports['GroundLXW_2'],)

                    elif index==1:

                        groundroute.side='right'

                        if label=='straight':

                            groundroute.source=(probe_cell.ports['GroundRXN_1'],)

                            groundroute.destination=(probe_cell.ports['GroundRXS_2'],)

                        elif label=='side':

                            groundroute.source=(probe_cell.ports['GroundRXE_1'],)

                            groundroute.destination=(probe_cell.ports['GroundRXE_2'],)

                    # groundroute.overhang=groundroute.set_auto_overhang(True)

                #signal routing
                for index,sigroute in enumerate([self.sig1trace,self.sig2trace]):

                    sigroute.side='auto'

                    sigroute.layer=(self.idt.layer,)

                    if index==0:

                        sigroute.source=(probe_cell.ports['SigN_1'],)

                        dest_port=pt._find_ports(device_cell,'bottom')

                        sigroute.destination=tuple(dest_port)

                        sigroute.trace_width=dest_port[0].width

                    elif index==1:

                        dest_port=pt._find_ports(device_cell,'top')

                        sigroute.source=(probe_cell.ports['SigS_2'],)

                        sigroute.destination=tuple(dest_port)

                        sigroute.trace_width=dest_port[0].width

            elif isinstance(self.probe,pc.GSProbe):

                raise ValueError("OnePortProbed with GSprobe to be implemented ")

            else:

                raise ValueError("OnePortProbed without GSG/GSprobe to be implemented ")

        def _draw_device_grounds(self,device_cell,probe_cell,label):

            output_cell=Device()

            lx_device_ports=[]

            rx_device_ports=[]

            gnd_ports=pt._find_ports(device_cell,'Ground')

            if not gnd_ports:

                return output_cell

            for p in gnd_ports:

                p_adj=Port(
                    name=p.name,
                    midpoint=p.midpoint,
                    width=probe_cell['Port1'].size[1],
                    orientation=p.orientation)

                if "LX" in p.name:

                    lx_device_ports.append(p_adj)

                elif "RX" in p.name:

                    rx_device_ports.append(p_adj)

            r=pc.MultiRouting()

            r.layer=self.gndlefttrace.layer

            if label=='side':

                r.source=tuple(pt._find_ports(probe_cell,'GroundLXW'))

            elif label=='straight':

                r.source=tuple(probe_cell.ports['GroundLXN_1'],probe_cell.ports['GroundLXS_2'])

            r.destination=tuple(lx_device_ports)

            r.clearance=pt._bbox_to_tuple(device_cell.bbox)

            r.side='left'

            output_cell.absorb(output_cell<<r.draw())

            if label=='side':

                r.source=tuple(pt._find_ports(probe_cell,'GroundRXE'))

            elif label=='straight':

                r.source=tuple(probe_cell.ports['GroundLXN_1'],probe_cell.ports['GroundLXS_2'])

            r.destination=tuple(rx_device_ports)

            r.side='right'

            output_cell.absorb(output_cell<<r.draw())

            return output_cell

        def get_components(self):

            supercomp=copy(super().get_components())

            supercomp.pop("SigTrace")

            supercomp.update({
                "Sig1Trace":pc.ParasiticAwareMultiRouting,
                "Sig2Trace":pc.ParasiticAwareMultiRouting})

            return supercomp

        def get_params(self):

            t=super().get_params()

            pt.pop_all_dict(t, [k for k in t if re.search('Sig1Trace',k) ])
            pt.pop_all_dict(t, [k for k in t if re.search('Sig2Trace',k) ])

            return t

    TwoPortProbed.__name__=f"TwoPortProbed {cls.__name__} with {probe.__name__}"

    return TwoPortProbed

# Device decorator

def add_compass(device : Device) -> Device:
    ''' add four ports at the bbox of a cell.

    Parameters
    ----------
    device : phidl.Device

    Returns
    -------
    device : phidl.Device.
    '''

    bound_cell=pg.compass(size=device.size).move(\
    origin=(0,0),destination=device.center)

    ports=port=bound_cell.get_ports()

    device.add_port(port=ports[0],name='N')
    device.add_port(port=ports[1],name='S')
    device.add_port(port=ports[2],name='E')
    device.add_port(port=ports[3],name='W')

    return device

def connect_ports(
    cell,
    tags='top',
    conn_dist=pt.Point(0,100),
    layers=LayoutDefault.layerTop):
    ''' connects all the ports in the cell with name matching a tag.

    Parameters:
    -----------
        cell : Device

        tags: tuple of str

        conn_dist: pt.Point
            offset from port location

        layer : tuple.
    '''

    if isinstance(tags,str):

        tags=tuple([tags])

    import pirel.pcells as pc

    connector=pc.MultiRouting()

    for tag in tags:

        if 'top' in tag:

            top_ports=pt._find_ports(cell,'top')

            top_conn=Port('top')

            top_conn.width=top_ports[0].width

            top_conn.midpoint=(pt.Point(cell.x,cell.ymax)+conn_dist).coord

            top_conn.orientation=270

            connector.layer=layers

            connector.source=tuple([top_conn])

            connector.destination=tuple(top_ports)

            connector.trace_width=top_ports[0].width

            connector.clearance=tuple(tuple(_) for _ in cell.bbox.tolist())

            connector.set_auto_overhang(True)

            tracecell=connector.draw()

            top_trace_ref=cell.add_ref(tracecell,alias='TopTrace')

            top_conn.orientation=90

            cell.add_port(top_conn)

        if 'bottom' in tag:

            bottom_conn=Port('bottom')

            bottom_ports=pt._find_ports(cell,'bottom')

            bottom_conn.width=bottom_ports[0].width

            bottom_conn.midpoint=(pt.Point(cell.x,cell.ymin)-conn_dist).coord

            bottom_conn.orientation=90

            connector.source=tuple(bottom_conn,)

            connector.destination=tuple(bottom_ports)

            connector.trace_width=bottom_ports[0].width

            connector.clearance=tuple(tuple(_) for _ in cell.bbox.tolist())

            connector.set_auto_overhang(True)

            tracecell=connector.draw()

            bottom_trace_ref=cell.add_ref(tracecell,alias='BottomTrace')

            bottom_conn.orientation=270

            cell.add_port(bottom_conn)

def add_pads(cell,pad,tags='top'):
    ''' add pad designs to a cell, connecting it to selected ports.

    Parameters:
    -----------
        cell : Device

        pad : pt.LayoutPart

        tags : iterable of str
            used to find ports
    '''

    if isinstance(tags,str):

        tags=tuple([tags])

    for tag in tags:

        ports=pt._find_ports(cell,tag)

        for port in ports:

            pad.port=port

            pad_ref=cell.add_ref(pad.draw())

            pad_ref.connect('conn',destination=port)

def add_vias(cell : Device, bbox, via : pt.LayoutPart, spacing : float = 0,tolerance: float = 0):

    ''' adds via pattern to cell with constraints.

    Parameters:
    -----------

    cell : Device
        where the vias will be located

    bbox : iterable
        x,y coordinates of box ll and ur to define vias patterns size

    via : pt.LayoutPart

    spacing : float

    tolerance : float (default 0)
        if not 0, used to determine via distance from target object border

    Returns:
    --------
    cell_out : Device
    '''

    bbox_cell=pg.bbox(bbox)

    nvias_x=int(np.floor(bbox_cell.xsize/(via.size+spacing)))

    nvias_y=int(np.floor(bbox_cell.ysize/(via.size+spacing)))

    if nvias_x==0 or nvias_y==0:

        raise ValueError("Via is too large for bbox !")

    via_cell=pt.draw_array(via.draw(),
        nvias_x,nvias_y,
        row_spacing=spacing,
        column_spacing=spacing)

    via_cell.move(
        origin=(via_cell.x,via_cell.y),
        destination=(bbox_cell.x,bbox_cell.y))

    tbr=[]

    for elem in via_cell.references:

        if not pt.is_cell_inside(elem,cell,tolerance):

            tbr.append(elem)

    via_cell.remove(tbr)

    cell.add_ref(via_cell,alias="Vias")

    # return cell_out

def _add_default_ground_vias(self,cell):

    if hasattr(self,'gndvia'):

        add_vias(cell,
            cell.bbox,
            self.gndvia,
            spacing=self.gndvia.size*1.25,
            tolerance=self.gndvia.size/2)

def attach_taper(cell : Device , port : Port , length : float , \
    width2 : float, layer=LayoutDefault.layerTop) :

    t=pg.taper(length=length,width1=port.width,width2=width2,layer=layer)

    t_ref=cell.add_ref(t)

    t_ref.connect(1,destination=port)

    new_port=t_ref.ports[2]

    new_port.name=port.name

    cell.absorb(t_ref)

    cell.remove(port)

    cell.add_port(new_port)

_allmodifiers=(
    makeScaled,addPad,addPartialEtch,
    addOnePortProbe,addLargeGround,
    makeArray,makeFixture,makeNpaths)
