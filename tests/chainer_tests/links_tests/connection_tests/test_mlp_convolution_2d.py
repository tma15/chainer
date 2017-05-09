import unittest

import mock
import numpy

import chainer
from chainer import cuda
from chainer import functions
from chainer import links
from chainer import testing
from chainer.testing import attr


@testing.parameterize(
    {'use_cudnn': 'always'},
    {'use_cudnn': 'never'},
)
class TestMLPConvolution2D(unittest.TestCase):

    def setUp(self):
        self.mlp = links.MLPConvolution2D(
            3, (96, 96, 96), 11, activation=functions.sigmoid)
        self.x = numpy.zeros((10, 3, 20, 20), dtype=numpy.float32)

    def test_init(self):
        self.assertIs(self.mlp.activation, functions.sigmoid)

        self.assertEqual(len(self.mlp), 3)
        for i, conv in enumerate(self.mlp):
            self.assertIsInstance(conv, links.Convolution2D)
            if i == 0:
                self.assertEqual(conv.W.data.shape, (96, 3, 11, 11))
            else:
                self.assertEqual(conv.W.data.shape, (96, 96, 1, 1))

    def check_call(self, x_data):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            x = chainer.Variable(x_data)
            actual = self.mlp(x)
            act = functions.sigmoid
            expect = self.mlp[2](act(self.mlp[1](act(self.mlp[0](x)))))
        numpy.testing.assert_array_equal(
            cuda.to_cpu(expect.data), cuda.to_cpu(actual.data))

    def test_call_cpu(self):
        self.check_call(self.x)

    @attr.gpu
    def test_call_gpu(self):
        self.mlp.to_gpu()
        self.check_call(cuda.to_gpu(self.x))


@testing.parameterize(
    {'use_cudnn': 'always'},
    {'use_cudnn': 'never'},
)
@attr.cudnn
class TestMLPConvolution2DCudnnCall(unittest.TestCase):

    def setUp(self):
        self.mlp = links.MLPConvolution2D(
            3, (96, 96, 96), 11, activation=functions.sigmoid)
        self.mlp.to_gpu()
        self.x = cuda.cupy.zeros((10, 3, 20, 20), dtype=numpy.float32)
        self.gy = cuda.cupy.zeros((10, 96, 10, 10), dtype=numpy.float32)

    def forward(self):
        x = chainer.Variable(self.x)
        return self.mlp(x)

    def test_call_cudnn_forward(self):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            with mock.patch('cupy.cudnn.cudnn.convolutionForward') as func:
                self.forward()
                self.assertEqual(func.called,
                                 chainer.should_use_cudnn('>=auto'))

    def test_call_cudnn_backrward(self):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            y = self.forward()
            y.grad = self.gy
            if cuda.cudnn.cudnn.getVersion() >= 3000:
                patch = 'cupy.cudnn.cudnn.convolutionBackwardData_v3'
            else:
                patch = 'cupy.cudnn.cudnn.convolutionBackwardData_v2'
            with mock.patch(patch) as func:
                y.backward()
                self.assertEqual(func.called,
                                 chainer.should_use_cudnn('>=auto'))


@testing.parameterize(*testing.product({
    'use_cudnn': ['always', 'never'],
    'mlpconv_args': [
        ((None, (96, 96, 96), 11), {'activation': functions.sigmoid}),
        (((96, 96, 96), 11), {'activation': functions.sigmoid})
    ]
}))
class TestMLPConvolution2DShapePlaceholder(unittest.TestCase):

    def setUp(self):
        args, kwargs = self.mlpconv_args
        self.mlp = links.MLPConvolution2D(*args, **kwargs)
        self.x = numpy.zeros((10, 3, 20, 20), dtype=numpy.float32)

    def test_init(self):
        self.assertIs(self.mlp.activation, functions.sigmoid)
        self.assertEqual(len(self.mlp), 3)

    def check_call(self, x_data):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            x = chainer.Variable(x_data)
            actual = self.mlp(x)
            act = functions.sigmoid
            expect = self.mlp[2](act(self.mlp[1](act(self.mlp[0](x)))))
        numpy.testing.assert_array_equal(
            cuda.to_cpu(expect.data), cuda.to_cpu(actual.data))
        for i, conv in enumerate(self.mlp):
            self.assertIsInstance(conv, links.Convolution2D)
            if i == 0:
                self.assertEqual(conv.W.data.shape, (96, 3, 11, 11))
            else:
                self.assertEqual(conv.W.data.shape, (96, 96, 1, 1))

    def test_call_cpu(self):
        self.check_call(self.x)

    @attr.gpu
    def test_call_gpu(self):
        self.mlp.to_gpu()
        self.check_call(cuda.to_gpu(self.x))


testing.run_module(__name__, __file__)
