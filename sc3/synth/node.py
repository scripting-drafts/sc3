"""Node.sc"""

import logging

from ..base import utils as utl
from ..base import responders as rpd
from ..base import functions as fn
from ..base import model as mdl
from ..base import stream as stm
from ..base import clock as clk
from . import server as srv
from . import synthdesc as sdc
from . import _graphparam as gpp


__all__ = ['Group', 'ParGroup', 'Synth']


_logger = logging.getLogger(__name__)


class Node(gpp.NodeParameter):
    '''Base class for ``Group`` and ``Synth``.

    This class is not used directly but though its subclasses, ``Synth``
    and ``Group`` (or ``ParGroup``), which represent synth or group
    nodes on the server.

    Node objects which you explicitly free using the methods ``free``
    or ``release`` will have their ``group`` instance variable set to
    ``None``. However, objects which are automatically freed after a
    certain time (for instance by an ``EnvGen`` with a done action of 2)
    will not. This keeps the implementation of the classes simple and
    lightweight.

    To have the current state of a node tracked you can register it
    with an instance of ``NodeWatcher``, either by calling register on
    the ``Node`` instance or on the ``NodeWatcher`` singleton. This will
    enable two variables, ``is_playing`` and ``is_running``, which you
    can use for checking purposes.

    '''

    add_actions = {
        # Traditional.
        'addToHead': 0,
        'addToTail': 1,
        'addBefore': 2,
        'addAfter': 3,
        'addReplace': 4,
        # Simple.
        'head': 0,
        'tail': 1,
        'before': 2,
        'after': 3,
        'replace': 4,
        # Shortcut.
        'h': 0, 't': 1, 'b': 2, 'a': 3, 'r': 4,
        # // valid action numbers should stay the same
        0: 0, 1: 1, 2: 2, 3: 3, 4: 4
    }

    _register_all = False

    def __init__(self):
        super(gpp.NodeParameter, self).__init__(self)

    def _init_register(self, register):
        self._is_playing = None  # None (not watched/no info), True or False
        self._is_running = None  # None (not watched/no info), True or False
        if register or Node._register_all:
            self.register()

    @property
    def is_playing(self):
        '''bool : Return `True` if the node is in the server.

        The node must have been registered for this property to be active.

        '''

        return self._is_playing

    @property
    def is_running(self):
        '''bool : Return `True` if the node is running, i.e. not paused.

        Nodes can be paused by sending a '/n_run' message using the
        method ``run``. The node must have been registered for this
        property to be active.

        '''

        return self._is_running

    @classmethod
    def basic_new(cls, server=None, node_id=None):
        '''Instantiate a node object without creating it on the server.

        Parameters
        ----------
        server : Server
            The target server. If `None` default server will be used.
        node_id : int
            ID of the node. If not supplied one will be generated by
            the server's ``NodeIDAllocator``. Normally there is no need
            to supply an ID. Default is `None`.

        '''

        obj = cls.__new__(cls)  # basic_new doesn't send therefore can't call __init__
        super(gpp.NodeParameter, obj).__init__(obj)
        obj.server = server or srv.Server.default
        if node_id is None:
            obj.node_id = obj.server._next_node_id()
        else:
            obj.node_id = node_id
        obj.group = None
        obj._is_playing = None  # None (not watched/no info), True or False
        obj._is_running = None  # None (not watched/no info), True or False
        return obj

    @classmethod
    def _action_number_for(cls, add_action):
        return cls.add_actions[add_action]

    def free(self, send_flag=True):
        '''Stop this node and free it from its parent group on the server.

        Once a node has been freed, is not possible to restart it.

        Parameters
        ----------
        send_flag : bool
            Indicate whether the free message should be sent.
            If `False` an '/n_free' message will not be sent to this
            node's server, but its is_playing and is_running properties
            will be set to false. Default is `True`.

        '''

        if send_flag:
            self.server.addr.send_msg('/n_free', self.node_id) # 11
        self.group = None

    def run(self, flag=True):
        '''Set the running state of this node.

        Parameters
        ----------
        flagprBootInProcessServer : bool
            `False` will pause the node without freeing it.
            Default is `True`.

        '''

        self.server.addr.send_msg('/n_run', self.node_id, int(flag)) # 12

    def map(self, *args):
        '''Map controls in this node to read from control rate buses.

        Parameters
        ----------
        *args : tuple(str | int, ControlBus | int, ...)
            A sequence alternating controls and buses to map to each
            control.

        Notes
        -----
        Controls are defined in a ``SynthDef`` as parameters or
        instances of ``Control`` ugens or its subclasses. They are
        specified here using either strings (names) or indices
        (position), and are listed in pairs with control bus indices
        or objects.

        To unmap a control set the bus value to -1.

        If the node is a group, mapping propagates recursively to the
        controls of all nodes within the group.

        '''

        self.server.addr.send_msg(
            '/n_map', self.node_id,
            *gpp.node_param(args)._as_control_input())

    def mapa(self, *args):
        '''Map controls in this node to read from audio rate buses.

        Parameters
        ----------
        *args : tuple(str | int, ControlBus | int, ...)
            A sequence alternating controls and buses to map to each
            control.

        Notes
        -----
        Controls are defined in a ``SynthDef`` as parameters or
        instances of ``Control`` ugens or its subclasses. They are
        specified here using either strings (names) or indices
        (position), and are listed in pairs with audio bus indices
        or objects.

        To unmap a control set the bus value to -1.

        If the node is a group, mapping propagates recursively to the
        controls of all nodes within the group.

        '''

        self.server.addr.send_msg(
            '/n_mapa', self.node_id,
            *gpp.node_param(args)._as_control_input())

    def mapn(self, *args):
        '''Map adjacent controls in this node to read from control rate buses.

        .. warning::
            This message only maps adjacent controls from multichannel
            buses if controls are set by position (as int). Setting
            controls by name (as str) has the same effect as ``map``.

        Parameters
        ----------
        *args : tuple(str | int, ControlBus | int, ...)
            A sequence alternating controls and buses to map to each
            control.

        Notes
        -----
        Multichannel buses will sequentially map to adjacent controls
        if the control is specified by index (position).
        See also ``map``.

        '''

        data = self._process_mn_args(args)
        self.server.addr.send_msg(*(['/n_mapn', self.node_id] + data))

    def mapan(self, *args):
        '''Map adjacent controls in this node to read from audio rate buses.

        .. warning::
            This message only maps adjacent controls from multichannel
            buses if controls are set by position (as int). Setting
            controls by name (as str) has the same effect as ``mapa``.

        Parameters
        ----------
        *args : tuple(str | int, AudioBus | int, ...)
            A sequence alternating controls and buses to map to each
            control.

        Notes
        -----
        Multichannel buses will sequentially map to adjacent controls
        if the control is specified by index (position).
        See also ``mapa``.

        '''

        data = self._process_mn_args(args)
        self.server.addr.send_msg(*(['/n_mapan', self.node_id] + data))

    @staticmethod
    def _process_mn_args(tpl):
        data = []
        for control, bus in utl.gen_cclumps(tpl, 2):
            if isinstance(bus, int):
                data.extend([
                    gpp.node_param(control)._as_control_input(), bus, 1])
            else:
                data.extend([
                    gpp.node_param(control)._as_control_input(),
                    bus.index, bus.channels])
        return data

    def set(self, *args):
        '''Set controls' values for this node.

        .. warning::
            This message only maps adjacent controls if they are set
            by position (as int).

        Parameters
        ----------
        *args : tuple(str | int, float | int, ...)
            A sequence alternating controls' names or positions and
            values.

        Notes
        -----
        Values that are lists or tuples are sent using the OSC array
        type-tags. These values will be assigned to subsequent controls
        in the manner of ``setn`` if the control are specified by
        position (as int).

        If the node is a group, mapping propagates recursively to the
        controls of all nodes within the group.

        '''

        self.server.addr.send_msg(
            '/n_set', self.node_id,  # 15
            *gpp.node_param(args)._as_osc_arg_list())

    def setn(self, *args):
        '''Set ranges of adjacent controls in this node to values.

        See ``set``.

        '''

        arg_list = []
        args = gpp.node_param(args)._as_control_input()
        for control, more_vals in utl.gen_cclumps(args, 2):
            if isinstance(more_vals, list):
                arg_list.extend([control, len(more_vals), *more_vals])
            else:
                arg_list.extend([control, 1, more_vals])

        self.server.addr.send_msg('/n_setn', self.node_id, *arg_list)  # 16

    def fill(self, cname, num_controls, value, *args):
        '''Set sequential ranges of controls in this node to a single value.

        Parameters
        ----------
        cname : str | int
            Control's name or position.
        num_controls : int
            Number of adjacent controls to set.
        value : float | int
            Value of the controls.
        *args : tuple(cname, num_controls, value)
            More control.

        '''

        self.server.addr.send_msg(
            '/n_fill', self.node_id,  # 17
            cname, num_controls, value,
            *gpp.node_param(args)._as_control_input())

    def release(self, time=None):
        '''Free the node using the `'gate'` control.

        Parameters
        ----------
        time : None | float | int
            The amount of time in seconds during which the node will
            release. If set to a value <= 0, the synth will release
            immediately. A `None` value will cause the synth to release
            using its envelope's normal release stage(s).

            Providing a releaseTime != `None` doesn't trigger a normal
            release, but a different behavior called `forced release`.
            This difference is particularly important for envelopes
            with a multi-node release stage, i.e. whose releaseNode is
            not their last node. See ``EnvGen`` `forced release`.

        Notes
        -----
        This method causes the receiver to be freed after the specified
        amount of time. This is a convenience method which assumes tha
        the synth contains an envelope generator (an ``EnvGen``,
        ``Linen``, or similar ugen) running a sustaining envelope and
        that this envelope's gate argument is set to a control called
        ``'gate'``.

        If the receiver is a group, all nodes within the group will be
        released.

        '''

        if time is not None:
            if time <= 0:
                time = -1
            else:
                time = -(time + 1)
        else:
            time = 0

        # Sends a bundle so it can be used as
        # counterpart of SynthDef__call__.
        self.server.addr.send_bundle(
            self.server.latency, ['/n_set', self.node_id, 'gate', time])  # 15

    def trace(self):
        self.server.addr.send_msg('/n_trace', self.node_id) # 10

    def query(self, action=None):
        if action is None:
            def action(cmd, node_id, parent, prev, next,
                       is_group, head=None, tail=None):
                group = is_group == 1
                node_type = 'Group' if group else 'Synth'
                msg = (f'{node_type}: {node_id}'
                       f'\n   parent: {parent}'
                       f'\n   prev: {prev}'
                       f'\n   next: {next}')
                if group:
                    msg += (f'\n   head: {head}'
                            f'\n   tail: {tail}')
                print(msg)

        rpd.OscFunc(
            lambda msg, *_: action(*msg),
            '/n_info', self.server.addr,
            arg_template=[self.node_id]).one_shot()
        self.server.addr.send_msg('/n_query', self.node_id)

    def register(self, playing=True, running=True):
        self.server._node_watcher.register(self, playing, running)

    def unregister(self):
        self.server._node_watcher.unregister(self)

    def on_free(self, action):
        def action_wrapper():
            fn.value(action, self)
            mdl.NotificationCenter.unregister(self, '/n_end', self)

        self.register()
        mdl.NotificationCenter.register(self, '/n_end', self, action_wrapper)

    def wait_for_free(self):
        condition = stm.Condition()
        self.on_free(lambda: condition.unhang())
        yield from condition.hang()

    def move_before(self, node):
        self.group = node.group
        self.server.addr.send_msg(
            '/n_before', self.node_id, node.node_id)  # 18

    def move_after(self, node):
        self.group = node.group
        self.server.addr.send_msg(
            '/n_after', self.node_id, node.node_id)  # 19

    def move_to_head(self, group=None):
        group = group or self.server.default_group
        group.move_node_to_head(self)

    def move_to_tail(self, group=None):
        group = group or self.server.default_group
        group.move_node_to_tail(self)


    ### Node parameter interface ###

    def _as_control_input(self):
        return self.node_id

    def _as_target(self):
        return self


# // common base for Group and ParGroup classes
class AbstractGroup(Node):
    '''Base class for ``Group`` and ``ParGroup``

    '''

    def __init__(self, target=None, add_action='addToHead', register=False):
        # // Immediately sends.
        super().__init__()
        target = gpp.node_param(target)._as_target()
        self.server = target.server
        self.node_id = self.server._next_node_id()
        add_action_id = type(self).add_actions[add_action]
        if add_action_id < 2:
            self.group = target
        else:
            self.group = target.group
        self._init_register(register)
        self.server.addr.send_msg(
            self.creation_cmd(), self.node_id,
            add_action_id, target.node_id)

    @classmethod
    def after(cls, node):
        return cls(node, 'addAfter')

    @classmethod
    def before(cls, node):
        return cls(node, 'addBefore')

    @classmethod
    def head(cls, group):
        return cls(group, 'addToHead')

    @classmethod
    def tail(cls, group):
        return cls(group, 'addToTail')

    @classmethod
    def replace(cls, node_to_replace):
        return cls(node_to_replace, 'addReplace')

    # // move Nodes to this group

    def move_node_to_head(self, node):
        node.group = self
        self.server.addr.send_msg('/g_head', self.node_id, node.node_id) # 22

    def move_node_to_tail(self, node):
        node.group = self
        self.server.addr.send_msg('/g_tail', self.node_id, node.node_id) # 23

    def free_all(self):
        # // free my children, but this node is still playing
        self.server.addr.send_msg('/g_freeAll', self.node_id) # 24

    def deep_free(self):
        self.server.addr.send_msg('/g_deepFree', self.node_id) # 50

    def dump_tree(self, controls=False):
        '''Ask the server to dump this node tree to stdout.

        Parameters
        ----------
        controls: bool
            If `True` also print synth controls with current values.

        '''

        self.server.addr.send_msg('/g_dumpTree', self.node_id, int(controls))

    def query_tree(self, controls=False, action=None, timeout=3):
        '''Query the groups's node tree.

        Parameters
        ----------
        controls: bool
            If `True` also request synth controls values.
        action: function
            A responder function that receives the data in JSON format.
        timeout: int | float
            Request timeout in seconds.

        '''

        done = False

        def resp_func(msg, *_):
            print_controls = bool(msg[1])
            key_name = f'Group({msg[2]})'
            outdct = dict()
            outdct[key_name] = dict()
            i = 2

            if msg[3] > 0:
                def dump_func(outdct, num_children):
                    nonlocal i
                    for _ in range(num_children):
                        if msg[i + 1] >= 0:
                            i += 2
                        else:
                            if print_controls:
                                i += msg[i + 3] * 2 + 1
                            i += 3
                        node_id = f'{msg[i]}'
                        if msg[i + 1] >= 0:
                            key_name = f'Group({node_id})'
                            outdct[key_name] = dict()
                            if msg[i + 1] > 0:
                                dump_func(outdct[key_name], msg[i + 1])
                        else:
                            key_name = f'Synth({node_id}, {msg[i + 2]})'
                            outdct[key_name] = dict()
                            if print_controls:
                                j = 0
                                for _ in range(msg[i + 3]):
                                    outdct[key_name][f'{msg[i + 4 + j]}'] =\
                                        msg[i + 5 + j]
                                    j += 2

                dump_func(outdct[key_name], msg[3])

            nonlocal done
            done = True

            if action:
                fn.value(action, outdct)
            else:
                self._pretty_tree(outdct)

        resp = rpd.OscFunc(resp_func, '/g_queryTree.reply', self.server.addr)
        resp.one_shot()

        def timeout_func():
            if not done:
                resp.free()
                _logger.warning(
                    f"server '{self.server.name}' failed to respond "
                    f"to '/g_queryTree' after {timeout} seconds")

        self.server.addr.send_msg('/g_queryTree', self.node_id, int(controls))
        clk.SystemClock.sched(timeout, timeout_func)

    def _pretty_tree(self, d, indent=0, tab=2):
        for key, value in d.items():
            _logger.info(' ' * tab * indent + str(key))
            if key.startswith('Synth'):
                log = ' ' * tab * (indent + 1)
                for k, v in value.items():
                    log += f'{k}: {v} '
                _logger.info(log)
            elif isinstance(value, dict):
                self._pretty_tree(value, indent+1)

    @staticmethod
    def creation_cmd():
        raise NotImplementedError()

    def __repr__(self):
        return f'{type(self).__name__}({self.node_id})'


class Group(AbstractGroup):
    '''Client-side representation of a group node on the server.

    '''

    @staticmethod
    def creation_cmd():
        return '/g_new' # 21


class ParGroup(AbstractGroup):
    @staticmethod
    def creation_cmd():
        return '/p_new' # 63


class RootNode(Group):
    '''Persistent root node group on the server.

    For each booted server the node tree structure is initialized with
    a root node of ID 0. This is intended for internal use only and
    should not be confused with the default group. Root nodes are
    always playing, always running, cannot be freed, or moved anywhere.
    Caching is used so that there is always one root node per server.::

        s = Server.default
        a = RootNode(s)
        b = RootNode(s)
        assert a is b

    Notes
    -----
    In general user nodes should not be added to the root node unless
    there is a specific reason to do so. Instead one should add nodes
    to the default group. This provides a known basic node order and
    protects functionality like Server.recorder, or other special
    objects.

    The default group is the default target for all new nodes, so when
    using object style nodes will normally not be added to the root
    node unless that is explicitly specified. See ``default group`` for
    more information.

    '''

    roots = dict()

    def __new__(cls, server=None):
        server = server or srv.Server.default
        if server.name in cls.roots:
            return cls.roots[server.name]
        else:
            obj = super(gpp.NodeParameter, cls).__new__(cls)
            obj.server = server
            obj.node_id = 0
            obj._is_playing = True  # Always true even if not watched.
            obj._is_running = True  # Always true even if not watched.
            obj.group = obj
            cls.roots[obj.server.name] = obj
            return obj

    def __init__(self, _=None):
        super(gpp.NodeParameter, self).__init__(self)

    def run(self):
        _logger.warning('run has no effect on RootNode')

    def free(self):
        _logger.warning('free has no effect on RootNode')

    def move_before(self):
        _logger.warning('moveBefore has no effect on RootNode')

    def move_after(self):
        _logger.warning('move_after has no effect on RootNode')

    def move_to_head(self):
        _logger.warning('move_to_head has no effect on RootNode')

    def move_to_tail(self):
        _logger.warning('move_to_tail has no effect on RootNode')

    @classmethod
    def free_all_roots(cls):  # Was freeAll, collision with instance method.
        '''Free all root nodes of all servers.

        '''

        for rn in cls.roots.values():
            rn.free_all()


class Synth(Node):
    '''Client-side representation of a synth node on the server.

    '''

    def __init__(self, def_name, args=None, target=None,
                 add_action='addToHead', register=False):
        # // Immediately sends.
        super().__init__()
        target = gpp.node_param(target)._as_target()
        self.server = target.server
        self.node_id = self.server._next_node_id()
        add_action_id = type(self).add_actions[add_action]
        if add_action_id < 2:
            self.group = target
        else:
            self.group = target.group
        self.def_name = def_name
        self._init_register(register)
        self.server.addr.send_msg(
            '/s_new', # 9
            self.def_name, self.node_id,
            add_action_id, target.node_id,
            *gpp.node_param(args or [])._as_osc_arg_list())

    # // does not send (used for bundling)
    @classmethod
    def basic_new(cls, def_name, server=None, node_id=None):
        obj = super().basic_new(server, node_id)
        obj.def_name = def_name
        return obj

    @classmethod
    def new_paused(cls, def_name, args=None, target=None, add_action='addToHead'):
        target = gpp.node_param(target)._as_target()
        server = target.server
        add_action_id = cls.add_actions[add_action]
        synth = cls.basic_new(def_name, server)
        if add_action_id < 2:
            synth.group = target
        else:
            synth.group = target.group
        synth.server.addr.send_bundle(
            None,
            [
                '/s_new', # 9
                synth.def_name, synth.node_id,
                add_action_id, target.node_id,
                *gpp.node_param(args or [])._as_osc_arg_list()
            ],
            [
                '/n_run', # 12
                synth.node_id, 0
            ]
        )
        return synth

    @classmethod
    def new_replace(cls, node_to_replace, def_name, args=None, same_id=False):  # Was *replace.
        if same_id:
            new_node_id = node_to_replace.node_id
        else:
            new_node_id = None
        server = node_to_replace.server
        synth = cls.basic_new(def_name, server, new_node_id)
        synth.server.addr.send_msg(
            '/s_new', # 9
            synth.def_name, synth.node_id,
            4, node_to_replace.node_id, # 4 -> 'addReplace'
            *gpp.node_param(args or [])._as_osc_arg_list())
        return synth

    @classmethod
    def grain(cls, def_name, args=None, target=None, add_action='addToHead'):
        # Uses node id -1 for transitory nodes.
        target = gpp.node_param(target)._as_target()
        server = target.server
        server.addr.send_msg(
            '/s_new', def_name, -1,  # 9
            cls.add_actions[add_action], target.node_id,
            *gpp.node_param(args or [])._as_osc_arg_list())

    @classmethod
    def after(cls, node, def_name, args=None):
        return cls(def_name, args, node, 'addAfter')

    @classmethod
    def before(cls, node, def_name, args=None):
        return cls(def_name, args, node, 'addBefore')

    @classmethod
    def head(cls, group, def_name, args=None):
        return cls(def_name, args, group, 'addToHead')

    @classmethod
    def tail(cls, group, def_name, args=None):
        return cls(def_name, args, group, 'addToTail')

    def replace(self, def_name, args=None, same_id=False):
        return type(self).new_replace(self, def_name, args, same_id)

    def get(self, index, action):
        def resp_func(msg, *_):
            # // The server replies with a message of the
            # // form: [/n_set, node ID, index, value].
            # // We want 'value' which is at index 3.
            fn.value(action, msg[3])

        rpd.OscFunc(
            resp_func, '/n_set', self.server.addr,
            arg_template=[self.node_id, index]).one_shot()

        self.server.addr.send_msg('/s_get', self.node_id, index)  # 44

    def getn(self, index, count, action):
        def resp_func(msg, *_):
            # // The server replies with a message of the form
            # // [/n_setn, node ID, index, count, *values].
            # // We want '*values' which are at indexes 4 and above.
            fn.value(action, msg[4:])

        rpd.OscFunc(
            resp_func, '/n_setn', self.server.addr,
            arg_template=[self.node_id, index]).one_shot()

        self.server.addr.send_msg('/s_getn', self.node_id, index, count)  # 45

    def seti(self, *args): # // args are [key, index, value, key, index, value ...]
        '''

        Notes
        -----
        This method has nothing to do with extraterrestrial intelligence.

        '''

        osc_msg = []
        synth_desc = sdc.SynthDescLib.at(self.def_name)
        if synth_desc is None:
            _logger.warning(
                f"message seti failed, SynthDef '{self.def_name}' "
                "not found in SynthDescLib")
            return
        for key, offset, value in utl.gen_cclumps(args, 3):
            if key in synth_desc.control_dict:
                cname = synth_desc.control_dict[key]
                if offset < cname.channels:
                    osc_msg.append(cname.index + offset)
                    if isinstance(value, list):
                        osc_msg.append(value[:cname.channels - offset]) # keep
                    else:
                        osc_msg.append(value)
        self.server.addr.send_msg(
            '/n_set', self.node_id,
            *gpp.node_param(osc_msg)._as_osc_arg_list())

    def __repr__(self):
        return f'{type(self).__name__}({self.def_name} : {self.node_id})'
