#!/usr/bin/env python3 -u
# coding: utf-8

__all__ = ["SlidingWindowSplitter", "ManualWindowSplitter", "temporal_train_test_split"]
__author__ = ["Markus Löning"]

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sktime.utils.validation.forecasting import check_fh
from sktime.utils.validation.forecasting import check_step_length
from sktime.utils.validation.forecasting import check_time_index
from sktime.utils.validation.forecasting import check_window_length

DEFAULT_STEP_LENGTH = 1
DEFAULT_WINDOW_LENGTH = 10
DEFAULT_FH = 1


class BaseTemporalCrossValidator:
    """Rolling window iterator that allows to split time series index into two windows,
    one containing observations used as feature data and one containing observations used as
    target data to be predicted. The target window has the length of the given forecasting horizon.

    Parameters
    ----------
    window_length : int
        Length of rolling window
    fh : array-like  or int, optional, (default=None)
        Single step ahead or array of steps ahead to forecast.
    """

    def __init__(self, fh=DEFAULT_FH, window_length=DEFAULT_WINDOW_LENGTH):
        self._window_length = check_window_length(window_length)
        self._fh = check_fh(fh)
        self._n_splits = None

    def split(self, y):
        raise NotImplementedError("abstract method")

    def get_n_splits(self, y=None):
        """
        Return number of splits.
        """
        raise NotImplementedError("abstract method")

    @property
    def fh(self):
        """Forecasting horizon"""
        return self._fh

    @property
    def window_length(self):
        """Window length"""
        return self._window_length


class SlidingWindowSplitter(BaseTemporalCrossValidator):

    def __init__(self, fh=DEFAULT_FH, window_length=DEFAULT_WINDOW_LENGTH, step_length=DEFAULT_STEP_LENGTH):
        self._step_length = check_step_length(step_length)
        super(SlidingWindowSplitter, self).__init__(fh=fh, window_length=window_length)

    def split(self, y):
        """Split time series using sliding window cross-validation"""

        # check time index
        if isinstance(y, pd.Series):
            y = y.index
        y = check_time_index(y)

        end = self._compute_end(y)
        fh = self.fh
        window_length = self._window_length
        step_length = self._step_length

        # split into windows
        for split_point in range(window_length, end, step_length):
            training_window = np.arange(split_point - window_length, split_point)
            test_window = split_point + fh - 1
            yield training_window, test_window

    def _compute_end(self, y):
        """Helper function to compute the end of the last window"""
        n_timepoints = len(y)
        fh = self.fh

        # end point is end of last window
        is_in_sample = np.all(fh <= 0)
        if is_in_sample:
            end = n_timepoints + 1
        else:
            fh_max = fh[-1]
            end = n_timepoints - fh_max + 1  #  non-inclusive end indexing

            # check if computed values are feasible with the provided index
            if self._window_length + fh_max > n_timepoints:
                raise ValueError(f"The window length and forecasting horizon are incompatible with the length of `y`")
        return end

    def get_n_splits(self, y=None):
        if y is None:
            raise ValueError(f"{self.__class__.__name__} requires `y` to compute the number of splits.")

        if isinstance(y, pd.Series):
            y = y.index
        y = check_time_index(y)

        end = self._compute_end(y)
        return np.int(np.ceil((end - self.window_length) / self.step_length))

    @property
    def step_length(self):
        """Step length"""
        return self._step_length


class ManualWindowSplitter(BaseTemporalCrossValidator):

    def __init__(self, cutoffs, fh=DEFAULT_FH, window_length=DEFAULT_WINDOW_LENGTH):
        self.cutoffs = cutoffs
        super(ManualWindowSplitter, self).__init__(fh=fh, window_length=window_length)

    def split(self, y):
        # check input
        if isinstance(y, pd.Series):
            y = y.index

        # check time index
        time_index = check_time_index(y)
        n_timepoints = len(time_index)

        # get parameters
        window_length = self._window_length
        fh = self._fh
        cutoffs = self.cutoffs

        self._n_splits = len(cutoffs)

        # check that all time points are in time index
        if not all(np.isin(cutoffs, time_index)):
            raise ValueError("`cutoff` points must be in time index.")

        if not all(np.isin(cutoffs - window_length + 1, time_index)):
            raise ValueError("Some windows would be outside of the time index; "
                             "please change `window length` or `time_points` ")

        # convert to zero-based integer index
        cutoffs = np.where(np.isin(time_index, cutoffs))[0]
        time_index = np.arange(n_timepoints)

        for time_point in cutoffs:
            training_window = time_index[time_point - window_length + 1:time_point + 1]
            test_window = time_index[time_point + fh]
            yield training_window, test_window

    def get_n_splits(self, y=None):
        return len(self.cutoffs)


def temporal_train_test_split(*arrays, test_size=None, train_size=None):
    """Split arrays or matrices into sequential train and test subsets
    Creates train/test splits over endogenous arrays an optional exogenous
    arrays. This is a wrapper of scikit-learn's ``train_test_split`` that
    does not shuffle.
    Parameters
    ----------
    *arrays : sequence of indexables with same length / shape[0]
        Allowed inputs are lists, numpy arrays, scipy-sparse
        matrices or pandas dataframes.
    test_size : float, int or None, optional (default=None)
        If float, should be between 0.0 and 1.0 and represent the proportion
        of the dataset to include in the test split. If int, represents the
        absolute number of test samples. If None, the value is set to the
        complement of the train size. If ``train_size`` is also None, it will
        be set to 0.25.
    train_size : float, int, or None, (default=None)
        If float, should be between 0.0 and 1.0 and represent the
        proportion of the dataset to include in the train split. If
        int, represents the absolute number of train samples. If None,
        the value is automatically set to the complement of the test size.
    Returns
    -------
    splitting : list, length=2 * len(arrays)
        List containing train-test split of inputs.

    References
    ----------
    ..[1]  adapted from https://github.com/alkaline-ml/pmdarima/blob/master/pmdarima/model_selection/_split.py
    """
    return train_test_split(
        *arrays,
        shuffle=False,
        stratify=None,
        test_size=test_size,
        train_size=train_size)