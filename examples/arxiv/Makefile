#!/usr/bin/env make
#
# Makefile to run the OGB conversion to Unigraph tool on some of its datasets.
#

# Temporary installation prefix setup on Linux.
PYVERSION = 3
PYTHON = python$(PYVERSION)

# Selected dataset.
DATASET = ogbn-arxiv
ROOT=/tmp/data/$(DATASET)

# Run the sampler on the X dataset.
graph:
	tfgnn_convert_ogb_dataset	\
		--dataset=$(DATASET)				\
		--ogb_datasets_dir=/tmp/ogb-preprocessed	\
		--output=$(ROOT)/graph

sample:
	tfgnn_graph_sampler		\
		--alsologtostderr				\
		--graph_schema=$(ROOT)/graph/schema.pbtxt	\
		--sampling_spec=$(PWD)/sampling_spec.pbtxt	\
		--output_samples=$(ROOT)/training/data@20

stats:
	tfgnn_sampled_stats			\
		--alsologtostderr					\
		--graph_schema=$(ROOT)/graph/schema.pbtxt		\
		--input_pattern=$(ROOT)/training/data-?????-of-00020	\
		--input_format=tfrecord					\
		--output_filename=$(ROOT)/training/stats.pbtxt

print:
	tfgnn_print_training_data	\
		--graph_schema=$(ROOT)/graph/schema.pbtxt	\
		--examples=$(ROOT)/training/data-?????-of-00020	\
		--file_format=tfrecord
