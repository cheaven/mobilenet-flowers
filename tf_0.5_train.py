import os
import numpy as np
import matplotlib.pyplot as plt
from preprocessing import inception_preprocessing
from Globals import *
import tensorflow as tf
from tensorflow.contrib import slim
from nets.mobilenet_v1 import *
from load_data import *
from tqdm import tqdm
from datetime import datetime


def new_mobilenet(images: tf.Tensor, num_classes: int, depth_multiplier: float, is_training: bool):
    with slim.arg_scope(mobilenet_v1_arg_scope(is_training=is_training)):
        nets, endpoints = mobilenet_v1_base(images, depth_multiplier=depth_multiplier)

    # add the new layer
    with tf.variable_scope('Flowers'):
        with slim.arg_scope([slim.conv2d],  padding='VALID', activation_fn=None, weights_initializer=slim.initializers.xavier_initializer_conv2d()):
            with slim.arg_scope([slim.batch_norm], activation_fn=tf.nn.relu6,  center=True, scale=True, decay=0.9997, epsilon=0.001):
                if depth_multiplier == 1.0 or depth_multiplier == 0.75:
                    # nets= [?,7,7,1024]
                    nets = slim.conv2d(nets, 512, (3, 3), padding='SAME')
                    nets = slim.batch_norm(nets)
                else:
                    pass
                # nets= [?,7,7,512]
                nets = slim.conv2d(nets, 256, (3, 3), stride=2)
                nets = slim.batch_norm(nets)
                # nets = [?,3,3,256]
                nets = slim.conv2d(nets, 128, (3, 3))
                nets = slim.batch_norm(nets)
                # nets = [?,1,1,128]
                nets = slim.conv2d(nets, 5, (1, 1), activation_fn=None)
                logits = tf.contrib.layers.softmax(nets)
    return logits, endpoints


def restore_ckpt(sess: tf.Session, ckptpath: str):
    variables_to_restore = slim.get_model_variables()
    loader = tf.train.Saver([var for var in variables_to_restore if 'MobilenetV1' in var.name])
    loader.restore(sess, ckptpath)


if __name__ == "__main__":
    depth_multiplier = 1.0
    learning_rate = 0.0005

    # generate the data
    namelist, labellist = get_filelist(TRAIN_PATH)
    dataset, epochstep = create_dataset(namelist, labellist, 8, parser)
    next_img, next_label = create_iter(dataset)
    # define the model
    predict, endpoints = new_mobilenet(next_img, CLASS_NUM, depth_multiplier, is_training=True)
    # define loss
    loss = tf.losses.softmax_cross_entropy(next_label, predict)
    # define train optimizer
    train_op = tf.train.AdamOptimizer(learning_rate=0.0007).minimize(loss)
    # calc the accuracy
    accuracy, accuracy_op = tf.metrics.accuracy(tf.argmax(next_label, axis=-1), tf.argmax(predict, axis=-1))

    epoch = 5
    with tf.Session() as sess:
        # init the model and restore the pre-train weight
        sess.run(tf.global_variables_initializer())
        sess.run(tf.local_variables_initializer())  # NOTE the accuracy must init local variable
        if depth_multiplier == 0.5:
            pre_ckpt = PRE_0_5_CKPT
        elif depth_multiplier == 0.75:
            pre_ckpt = PRE_0_75_CKPT
        elif depth_multiplier == 1.0:
            pre_ckpt = PRE_1_0_CKPT
        restore_ckpt(sess, pre_ckpt)
        # define the log
        writer = tf.summary.FileWriter(os.path.join(TRAIN_LOG_DIR, '{:2.1f}_{:%d_%H:%M:%S}'.format(depth_multiplier, datetime.now())), graph=sess.graph)
        tf.summary.scalar('loss', loss)
        tf.summary.scalar('accuracy', accuracy)
        merged = tf.summary.merge_all()
        # 使用进度条库
        for i in range(epoch):
            with tqdm(total=epochstep, bar_format='{n_fmt}/{total_fmt} |{bar}| {rate_fmt}{postfix}]', unit=' batch', dynamic_ncols=True) as t:
                for j in range(epochstep):
                    summary, _, losses, acc, _ = sess.run([merged, train_op, loss, accuracy, accuracy_op])
                    writer.add_summary(summary, i*epochstep+j)
                    t.set_postfix(loss='{:<5.3f}'.format(losses), acc='{:5.2f}%'.format(acc*100))  # 修改此处添加后缀
                    t.update()
