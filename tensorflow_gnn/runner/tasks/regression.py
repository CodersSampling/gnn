# Copyright 2021 The TensorFlow GNN Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Regression tasks."""
from __future__ import annotations

import abc
from typing import Callable, Optional, Sequence

import tensorflow as tf
import tensorflow_gnn as tfgnn
from tensorflow_gnn.runner import interfaces

AUTO = tf.keras.losses.Reduction.AUTO
Field = tfgnn.Field
GraphTensor = tfgnn.GraphTensor
LabelFn = Callable[[GraphTensor], tuple[GraphTensor, Field]]


class _Regression(interfaces.Task):
  """Regression abstract class.

  Any subclass must implement both `gather_activations` and `losses`, usually
  by inheriting from the below mix ins.
  """

  def __init__(self, units: int, label_fn: LabelFn):
    self._units = units
    self._label_fn = label_fn

  @abc.abstractmethod
  def gather_activations(self, inputs: GraphTensor) -> Field:
    raise NotImplementedError()

  def predict(self, inputs: tfgnn.GraphTensor) -> tf.Tensor:
    """Apply a linear head for regression.

    Args:
      inputs: A `tfgnn.GraphTensor` for regression.

    Returns:
      The regression logits.
    """
    tfgnn.check_scalar_graph_tensor(inputs, name="_Regression")
    activations = self.gather_activations(inputs)
    logits = tf.keras.layers.Dense(
        self._units,
        name="logits")(activations)  # Name seen in SignatureDef.
    return logits

  def preprocess(self, inputs: GraphTensor) -> tuple[GraphTensor, Field]:
    return self._label_fn(inputs)

  @abc.abstractmethod
  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    raise NotImplementedError()

  def metrics(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    """Regression metrics."""
    return (tf.keras.metrics.MeanSquaredError(),
            tf.keras.metrics.MeanAbsoluteError(),
            tf.keras.metrics.MeanSquaredLogarithmicError(),
            tf.keras.metrics.MeanAbsolutePercentageError())


class _GraphRegression(_Regression):
  """Graph context regression abstract class."""

  def __init__(self,
               node_set_name: str,
               *,
               units: int = 1,
               state_name: str = tfgnn.HIDDEN_STATE,
               reduce_type: str = "mean",
               label_fn: LabelFn):
    super().__init__(units, label_fn=label_fn)
    self._node_set_name = node_set_name
    self._state_name = state_name
    self._reduce_type = reduce_type

  def gather_activations(self, inputs: GraphTensor) -> tf.Tensor:
    return tfgnn.keras.layers.Pool(
        tfgnn.CONTEXT,
        self._reduce_type,
        node_set_name=self._node_set_name,
        feature_name=self._state_name)(inputs)


class _RootNodeRegression(_Regression):
  """Root node regression abstract class."""

  def __init__(self,
               node_set_name: str,
               *,
               units: int = 1,
               state_name: str = tfgnn.HIDDEN_STATE,
               label_fn: LabelFn):
    super().__init__(units, label_fn=label_fn)
    self._node_set_name = node_set_name
    self._state_name = state_name

  def gather_activations(self, inputs: GraphTensor) -> tf.Tensor:
    return tfgnn.keras.layers.ReadoutFirstNode(
        node_set_name=self._node_set_name,
        feature_name=self._state_name)(inputs)


class _MeanAbsoluteErrorLossMixIn:
  """Mean absolute error task."""

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (tf.keras.losses.MeanAbsoluteError(),)


class _MeanAbsolutePercentageErrorLossMixIn:
  """Mean absolute percentage error task."""

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (tf.keras.losses.MeanAbsolutePercentageError(),)


class _MeanSquaredErrorLossMixIn:
  """Mean squared error task."""

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (tf.keras.losses.MeanSquaredError(),)


class _MeanSquaredLogarithmicErrorLossMixIn:
  """Mean squared logarithmic error task."""

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (tf.keras.losses.MeanSquaredLogarithmicError(),)


class _MeanSquaredLogScaledError(tf.keras.losses.Loss):
  """Mean squared log scaled error task, see: go/xtzqv."""

  def __init__(self,
               reduction: tf.keras.losses.Reduction = AUTO,
               name: Optional[str] = None,
               *,
               alpha_loss_param: float,
               epsilon_loss_param: float):
    super().__init__(reduction, name)
    self._alpha_loss_param = alpha_loss_param
    self._epsilon_loss_param = epsilon_loss_param

  def call(self, y_true, y_pred):
    """See tf.keras.losses.Loss."""
    y_pred = tf.cast(tf.keras.activations.relu(y_pred), tf.float64)
    y_true = tf.cast(y_true, tf.float64)

    mse = tf.keras.losses.mean_squared_error(y_true, y_pred)
    msle = tf.math.reduce_mean(
        tf.math.squared_difference(
            tf.math.log(y_pred + self._epsilon_loss_param),
            tf.math.log(y_true + self._epsilon_loss_param)))

    mse = tf.debugging.check_numerics(mse, "mse")
    msle = tf.debugging.check_numerics(msle, "msle")

    return mse + self._alpha_loss_param * msle

  def get_config(self):
    config = super().get_config()
    config.update({
        "alpha_loss_param": self._alpha_loss_param,
        "epsilon_loss_param": self._epsilon_loss_param
    })
    return config


class _MeanAbsoluteLogarithmicErrorLoss(tf.keras.losses.Loss):
  """Mean absolute log scaled error task."""

  def call(self, y_true, y_pred):
    return _mean_absolute_logarithmic_error(y_true, y_pred)


class _MeanSquaredLogScaledErrorLossMixIn:
  """Mean squared log scaled error task."""

  def __init__(self,
               *args,
               alpha_loss_param: float = 5.,
               epsilon_loss_param: float = 1e-8,
               reduction: tf.keras.losses.Reduction = AUTO,
               name: Optional[str] = None,
               **kwargs):
    super().__init__(*args, **kwargs)
    self._alpha_loss_param = alpha_loss_param
    self._epsilon_loss_param = epsilon_loss_param
    self._reduction = reduction
    self._name = name

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (_MeanSquaredLogScaledError(
        self._reduction,
        self._name,
        alpha_loss_param=self._alpha_loss_param,
        epsilon_loss_param=self._epsilon_loss_param),)


def _mean_absolute_logarithmic_error(y_true, y_pred):
  """Computes the mean absolute logarithmic error between `y_true` and `y_pred`.

  loss = mean((log(y_true + 1) - log(y_pred + 1)), axis=-1)

  Args:
    y_true: Ground truth values. shape = `[batch_size, d0, .. dN]`.
    y_pred: The predicted values. shape = `[batch_size, d0, .. dN]`.

  Returns:
    Mean absolute logarithmic error values. shape = `[batch_size, d0, .. dN-1]`.
  """
  y_pred = tf.math.log1p(tf.convert_to_tensor(y_pred))
  y_true = tf.math.log1p(tf.cast(y_true, y_pred.dtype))
  return tf.math.reduce_mean(tf.abs(y_pred - y_true), axis=-1)


class _MeanAbsoluteLogarithmicErrorLossMixIn:
  """Mean absolute logarithmic error task."""

  def __init__(
      self,
      reduction: tf.keras.losses.Reduction = AUTO,
      name: Optional[str] = None,
      **kwargs):
    super().__init__(**kwargs)
    self._reduction = reduction
    self._name = name

  def losses(self) -> Sequence[Callable[[tf.Tensor, tf.Tensor], tf.Tensor]]:
    return (_MeanAbsoluteLogarithmicErrorLoss(self._reduction, self._name),)


class RootNodeMeanAbsoluteLogarithmicError(
    _MeanAbsoluteLogarithmicErrorLossMixIn, _RootNodeRegression
):
  """Root node mean absolute logarithmic error task."""

  def predict(self, inputs: tfgnn.GraphTensor) -> tf.Tensor:
    """Apply a head with ReLU for nonnegative regression.

    Args:
      inputs: A `tfgnn.GraphTensor` use for prediction.

    Returns:
      The nonnegative logits.
    """
    tfgnn.check_scalar_graph_tensor(
        inputs,
        name="RootNodeMeanAbsoluteLogarithmicError")
    activations = self.gather_activations(inputs)
    logits = tf.keras.layers.Dense(
        self._units,
        activation="relu",
        name="logits")(activations)  # Name seen in SignatureDef.
    return logits


class GraphMeanAbsoluteError(_MeanAbsoluteErrorLossMixIn, _GraphRegression):
  pass


class GraphMeanAbsolutePercentageError(_MeanAbsolutePercentageErrorLossMixIn,
                                       _GraphRegression):
  pass


class GraphMeanSquaredError(_MeanSquaredErrorLossMixIn, _GraphRegression):
  pass


class GraphMeanSquaredLogarithmicError(_MeanSquaredLogarithmicErrorLossMixIn,
                                       _GraphRegression):
  pass


class GraphMeanSquaredLogScaledError(_MeanSquaredLogScaledErrorLossMixIn,
                                     _GraphRegression):
  pass


class RootNodeMeanAbsoluteError(_MeanAbsoluteErrorLossMixIn,
                                _RootNodeRegression):
  pass


class RootNodeMeanAbsolutePercentageError(_MeanAbsolutePercentageErrorLossMixIn,
                                          _RootNodeRegression):
  pass


class RootNodeMeanSquaredError(_MeanSquaredErrorLossMixIn, _RootNodeRegression):
  pass


class RootNodeMeanSquaredLogarithmicError(_MeanSquaredLogarithmicErrorLossMixIn,
                                          _RootNodeRegression):
  pass


class RootNodeMeanSquaredLogScaledError(_MeanSquaredLogScaledErrorLossMixIn,
                                        _RootNodeRegression):
  pass
