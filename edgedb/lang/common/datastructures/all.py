##
# Copyright (c) 2008-2011 Sprymix Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import abc
import bisect
import collections
import sys


class _MarkerMeta(type):
    def __repr__(cls):
        repr_ = cls.__repr__
        if repr_ is object.__repr__:
            repr_ = type.__repr__
        return repr_(cls)

    def __str__(cls):
        return cls.__name__

class _Marker(metaclass=_MarkerMeta):
    def __init__(self):
        raise TypeError('%r cannot be instantiated' % self.__class__.__name__)

    def __str__(cls):
        return cls.__name__

    __repr__ = __str__

class _VoidMeta(_MarkerMeta):
    def __bool__(cls):
        return False


class Void(_Marker, metaclass=_VoidMeta):
    pass


class GenericWrapperMeta(abc.ABCMeta):

    def __init__(cls, name, bases, dict):
        super().__init__(name, bases, dict)

        write_methods = set()
        read_methods = set()

        for i in range(0, len(cls.__mro__) - 1):
            lst = getattr(cls, '_' + cls.__mro__[i].__name__ + '__read_methods', set())
            read_methods.update(lst)
            lst = getattr(cls, '_' + cls.__mro__[i].__name__ + '__write_methods', set())
            write_methods.update(lst)

        cls.read_methods = read_methods
        cls.write_methods = write_methods

        cls._sethook('read')
        cls._sethook('write')


class GenericWrapper(object, metaclass=GenericWrapperMeta):
    write_methods = ()
    read_methods = ()

    @classmethod
    def _sethook(cls, hookname):
        hookmethod = '_' + hookname + '_hook'
        if hasattr(cls, hookmethod):
            hook = getattr(cls, hookmethod)
            methods = getattr(cls, hookname + '_methods')

            if hook:
                for method in methods:
                    setattr(cls, method + '_orig', getattr(cls, method, None))
                    setattr(cls, method, cls._gethook(hook, method))

    @classmethod
    def _gethook(cls, hook, method):
        def hookbody(self, *args, **kwargs):
            original = getattr(cls, method + '_orig', None)
            if not original:
                raise NotImplementedError
            hook(self, method, *args, **kwargs)
            return original(self, *args, **kwargs)

        return hookbody


class Container(GenericWrapper):
    __read_methods = ('__contains__',)


class Hashable(GenericWrapper):
    __read_methods = ('__hash__',)


class Iterable(GenericWrapper):
    __read_methods = ('__iter__',)


class Sized(GenericWrapper):
    __read_methods = ('__len__',)


class Callable(GenericWrapper):
    __read_methods = ('__call__',)


class Sequence(Sized, Iterable, Container):
    __read_methods = ('__getitem__', '__reversed__', 'index', 'count')


class MutableSequence(Sequence):
    __write_methods = ('__setitem__', '__delitem__', 'insert', 'append', 'reverse', 'extend', 'pop', 'remove',
                       '__iadd__')


class Set(Sized, Iterable, Container):
    __read_methods = ('__le__', '__lt__', '__eq__', '__ne__', '__gt__', '__ge__', '__and__', '__or__',
                      '__sub__', '__xor__', 'isdisjoint')

class MutableSet(Set):
    __write_methods = ('add', 'discard', 'clear', 'pop', 'remove', '__ior__', '__iand__', '__ixor__',
                       '__isub__')


class Mapping(Sized, Iterable, Container):
    __read_methods = ('__getitem__', '__contains__', 'keys', 'items', 'values', 'get', '__eq__', '__ne__')


class MutableMapping(Mapping):
    __write_methods = ('__setitem__', '__delitem__', 'pop', 'popitem', 'clear', 'update')


class SetWrapper(set, MutableSet):

    __write_methods = ('update', 'intersection_update', 'difference_update', 'symmetric_difference_update')

    __read_methods = ('issubset', 'issuperset', 'union', 'intersection', 'difference', 'symmetric_difference')

    original_base = set


class ListWrapper(list, MutableSequence):
    original_base = list


class SetView(collections.Set):
    def __init__(self, set):
        self._set = set

    def __contains__(self, item):
        return item in self._set

    def __iter__(self):
        return iter(self._set)

    def __len__(self):
        return len(self._set)


class SortedList(list):
    """
    A list that maintains it's order by a given criteria
    """

    def __init__(self, data=None):
        if data is None:
            data = []

        super(SortedList, self).__init__(data)

        self.sort()
        self.appending = False
        self.extending = False
        self.inserting = False

    def append(self, x):
        if not self.appending:
            self.appending = True
            bisect.insort_right(self, x)
            self.appending = False
        else:
            super(SortedList, self).append(x)

    def extend(self, L):
        if not self.extending:
            self.extending = True
            for x in L:
                bisect.insort_right(self, x)
            self.extending = False
        else:
            super(SortedList, self).extend(L)

    def insert(self, i, x):
        if not self.inserting:
            self.inserting = True
            bisect.insort_right(self, x)
            self.inserting = False
        else:
            super(SortedList, self).insert(i, x)


class BaseOrderedSet(collections.MutableSet):

    def __init__(self, iterable=None):
        self.map = collections.OrderedDict()
        if iterable is not None:
            self.update(iterable)

    @staticmethod
    def key(item):
        return item

    def add(self, key):
        k = self.key(key)
        if k not in self.map:
            self.map[k] = key

    def discard(self, key):
        key = self.key(key)
        if key in self.map:
            self.map.pop(key)

    def popitem(self, last=True):
        key, value = self.map.popitem(last)
        return key

    update = collections.MutableSet.__ior__
    difference_update = collections.MutableSet.__isub__
    symmetric_difference_update = collections.MutableSet.__ixor__
    intersection_update = collections.MutableSet.__iand__

    def __len__(self):
        return len(self.map)

    def __contains__(self, key):
        key = self.key(key)
        return key in self.map

    def __iter__(self):
        return iter(list(self.map.values()))

    def __reversed__(self):
        return reversed(self.map)

    def __repr__(self):
        if not self:
            return '%s()' % (self.__class__.__name__,)
        return '%s(%r)' % (self.__class__.__name__, list(self))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return len(self) == len(other) and list(self) == list(other)
        elif other is None:
            return False
        else:
            return not self.isdisjoint(other)

    def copy(self):
        return self.__class__(self)

    def clear(self):
        self.map.clear()


class OrderedSet(BaseOrderedSet, collections.MutableSequence):

    def __getitem__(self, key):
        # XXX
        return list(self.map.keys())[key]

    def __setitem__(self, slice):
        raise NotImplementedError

    def __delitem__(self, slice):
        raise NotImplementedError

    def __contains__(self, key):
        return key in self.map

    append = BaseOrderedSet.add

    def appendleft(self, key):
        self.add(key)
        k = self.key(key)
        self.map.move_to_end(k, last=False)

    def insert(self, pos, item):
        raise NotImplementedError

    def index(self, key):
        #XXX
        return list(self.map.keys()).index(key)

    def count(self, key):
        return int(key in self)


class ExtendedSet(collections.MutableSet):
    def __init__(self, *args, key=hash, **kwargs):
        self._set = set()
        self._key = key
        self._index = set()

        if args:
            self.update(args[0])

    def __contains__(self, item):
        return self._key(item) in self._index

    def __iter__(self):
        return iter(self._set)

    def __len__(self):
        return len(self._set)

    def add(self, item):
        self._index.add(self._key(item))
        self._set.add(item)

    def discard(self, item):
        self._index.discard(self._key(item))
        self._set.discard(item)

    def remove(self, item):
        self._index.remove(self._key(item))
        self._set.remove(item)

    def clear(self):
        self._index.clear()
        self._set.clear()

    def copy(self):
        return self.__class__(self, key=self._key)

    update = collections.MutableSet.__ior__
    difference_update = collections.MutableSet.__isub__
    symmetric_difference_update = collections.MutableSet.__ixor__
    intersection_update = collections.MutableSet.__iand__


class OrderedSetWrapper(OrderedSet, MutableSet, MutableSequence):
    original_base = OrderedSet


class OrderedIndex(BaseOrderedSet, collections.MutableMapping):
    def __init__(self, iterable=None, *, key=None):
        self.key = key or hash
        super().__init__(iterable)

    def keys(self):
        return self.map.keys()

    def values(self):
        return self.map.values()

    def items(self):
        return self.map.items()

    def __getitem__(self, key):
        try:
            return self.map[key]
        except KeyError:
            return self.map[self.key(key)]

    def __setitem__(self, item):
        key = self.key(item)
        self.map[key] = item

    def __delitem__(self, item):
        key = self.key(item)
        del self.map[key]

    def __sx_serialize__(self):
        return list(self.map.values())


class StrictOrderedIndex(OrderedIndex):
    def __setitem__(self, item):
        if item in self:
            raise ValueError('item %s is already present in the index' % item)
        super().__setitem__(item)


class Record(type):
    def __new__(mcls, name, fields, default=None):
        dct = {'_fields___': fields, '_default___': default}
        bases = (RecordBase,)
        return super(Record, mcls).__new__(mcls, name, bases, dct)

    def __init__(mcls, name, fields, default):
        pass


class RecordBase:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k not in self.__class__._fields___:
                raise TypeError('__init__() got an unexpected keyword argument %s' % k)
            setattr(self, k, v)

        for k in set(self.__class__._fields___) - set(kwargs.keys()):
            setattr(self, k, self.__class__._default___)


    def __setattr__(self, name, value):
        if name not in self.__class__._fields___:
            raise AttributeError('%s has no attribute %s' % (self.__class__.__name__, name))
        super().__setattr__(name, value)

    def __eq__(self, tup):
        if not isinstance(tup, tuple):
            return NotImplemented

        return tuple(self) == tup

    def __getitem__(self, index):
        return getattr(self, self.__class__._fields___[index])

    def __iter__(self):
        for name in self.__class__._fields___:
            yield getattr(self, name)

    def __len__(self):
        return len(self.__class__._fields___)

    def items(self):
        for name in self.__class__._fields___:
            yield name, getattr(self, name)

    def keys(self):
        return iter(self.__class__._fields___)

    def __str__(self):
        f = ', '.join(str(v) for v in self)
        if len(self) == 1:
            f += ','
        return '(%s)' % f

    __repr__ = __str__


class xvalue:
    """xvalue is a "rich" value that can have an arbitrary set of additional
    attributes attached to it."""


    __slots__ = ('value', 'attrs')

    def __init__(self, value, **attrs):
        self.value = value
        self.attrs = attrs

    def __repr__(self):
        attrs = ', '.join('%s=%r' % (k, v) for k, v in self.attrs.items())
        return '<xvalue "%r"; %s>' % (self.value, attrs)

    def __eq__(self, other):
        if not isinstance(other, xvalue):
            return NotImplemented

        return self.value == other.value and self.attrs == other.attrs

    def __hash__(self):
        return hash((self.value, frozenset(self.attrs.items())))

    __str__ = __repr__


class StrSingleton(str):
    def __new__(cls, val=''):
        name = cls._map.get(val)
        if name:
            return sys.modules[cls.__module__].__dict__.get(name, str.__new__(cls, val))
        else:
            raise ValueError('invalid value for %s: %s' % (cls.__name__, val))

    @classmethod
    def keys(cls):
        return iter(cls._map.values())

    @classmethod
    def values(cls):
        return iter(cls._map.keys())


class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
