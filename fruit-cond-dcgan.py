"""
Conditional Deep Conv GAN to generate fruits images (Under construction)
"""

import sys
import os

from keras.datasets import mnist
from keras.models import Sequential, Model
from keras.models import load_model
from keras.layers import Input, Dense, Reshape, Flatten, Dropout, multiply
from keras.layers import BatchNormalization, Activation, Embedding, concatenate
from keras.layers import ZeroPadding2D, MaxPooling2D
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.optimizers import Adam
from keras.utils.np_utils import to_categorical
from PIL import Image

import matplotlib.pyplot as plt
import numpy as np


class FruitCondDCGanModel:

    def __init__(self, image_size=48):

        # hyper parameter
        self.latent_dim = 100

        self.img_rows = image_size
        self.img_cols = image_size
        self.channels = 3
        self.img_shape = (self.img_rows, self.img_cols, self.channels)

        self.model_dir = "saved_models"

        dataset = "fruit"

        if(dataset == "mnist"):
            # Load the dataset
            (self.x_train, self.y_train), (_, _) = mnist.load_data()
            self.x_train = np.expand_dims(self.x_train, axis=3)

            self.num_classes = 10
            self.channels = 1
            self.img_rows = 28
            self.img_cols = 28

        else:
            # prepare train data
            self.prepare_train_data()

        optimizer = Adam(0.0002, 0.5)

        # Build and compile the discriminator
        self.discriminator = self.build_discriminator()
        self.discriminator.compile(loss=['binary_crossentropy'],
                                   optimizer=optimizer,
                                   metrics=['accuracy'])

        # Build the generator
        self.generator = self.build_generator()

        # The generator takes noise and the target label as input
        # and generates the corresponding digit of that label
        noise = Input(shape=(100,))
        label = Input(shape=(1,))
        img = self.generator([noise, label])

        # For the combined model we will only train the generator
        self.discriminator.trainable = False

        # The discriminator takes generated image as input and determines validity
        # and the label of that image
        valid = self.discriminator([img, label])

        # The combined model  (stacked generator and discriminator)
        # Trains generator to fool discriminator
        self.combined = Model([noise, label], valid)
        self.combined.compile(loss=['binary_crossentropy'],
                              optimizer=optimizer)

    def build_discriminator(self):

        # image part
        model = Sequential()
        model.add(
            Conv2D(64, (5, 5),
                   padding='same',
                   input_shape=self.img_shape)
        )
        model.add(Activation('tanh'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Conv2D(128, (5, 5)))
        model.add(Activation('tanh'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Flatten())
        model.add(Dense(self.latent_dim))

        model.summary()

        img = Input(shape=self.img_shape)
        img_vector = model(img)
        print("D img_vector.shape:", img_vector.shape)

        # label part
        label = Input(shape=(1,), dtype='int32')
        label_vector = Flatten()(
            Embedding(self.num_classes, self.latent_dim)(label))
        print("D label_vector.shape:", label_vector.shape)

        merged_vector = concatenate([img_vector, label_vector])
        print("D merged_vector.shape:", merged_vector.shape)

        output = Dense(self.latent_dim)(merged_vector)

        output = Dense(1,)(output)

        output = Activation('sigmoid')(output)

        d_model = Model([img, label], output)

        d_model.summary()

        return d_model

    def build_generator(self):

        conv_img_size = int(self.img_rows / 4)

        model = Sequential()
        model.add(Dense(input_dim=self.latent_dim * 2, units=1024))
        model.add(Activation('tanh'))
        model.add(Dense(128*conv_img_size*conv_img_size))
        model.add(BatchNormalization())
        model.add(Activation('tanh'))
        model.add(Reshape((conv_img_size, conv_img_size, 128),
                          input_shape=(128*conv_img_size*conv_img_size,)))
        model.add(UpSampling2D(size=(2, 2)))
        model.add(Conv2D(64, (5, 5), padding='same'))
        model.add(Activation('tanh'))
        model.add(UpSampling2D(size=(2, 2)))
        model.add(Conv2D(self.channels, (5, 5), padding='same'))
        model.add(Activation('tanh'))

        noise = Input(shape=(self.latent_dim,))
        label = Input(shape=(1,), dtype='int32')
        label_embedding = Flatten()(Embedding(self.num_classes,
                                              self.latent_dim)(label))

        print("noise.shape:", noise.shape)
        print("label_embedding.shape:", label_embedding.shape)

        model_input = concatenate([noise, label_embedding])

        print("model_input.shape:", model_input.shape)

        img = model(model_input)

        g_model = Model([noise, label], img)
        g_model.summary()

        return g_model

    def train(self, epochs, batch_size=128, sample_interval=50):

        (X_train, y_train) = self.x_train, self.y_train

        # Configure input
        X_train = (X_train.astype(np.float32) - 127.5) / 127.5
        y_train = y_train.reshape(-1, 1)

        print("X_train.shape", X_train.shape)
        print("y_train.shape", y_train.shape)

        # Adversarial ground truths
        valid = np.ones((batch_size, 1))
        fake = np.zeros((batch_size, 1))

        for epoch in range(epochs):

            # ---------------------
            #  Train Discriminator
            # ---------------------

            # Select a random half batch of images
            idx = np.random.randint(0, X_train.shape[0], batch_size)
            imgs, labels = X_train[idx], y_train[idx]

            # Sample noise as generator input
            noise = np.random.normal(0, 1, (batch_size, 100))

            # Generate a half batch of new images
            gen_imgs = self.generator.predict([noise, labels])

            # Train the discriminator
            d_loss_real = self.discriminator.train_on_batch(
                [imgs, labels], valid)

            d_loss_fake = self.discriminator.train_on_batch(
                [gen_imgs, labels], fake)

            d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

            # ---------------------
            #  Train Generator
            # ---------------------

            # Condition on labels
            sampled_labels = np.random.randint(
                0, self.num_classes, batch_size).reshape(-1, 1)

            # Train the generator
            g_loss = self.combined.train_on_batch(
                [noise, sampled_labels], valid)

            # Plot the progress
            print("%d [D loss: %f, acc.: %.2f%%] [G loss: %f]" %
                  (epoch, d_loss[0], 100*d_loss[1], g_loss))

            # If at save interval => save generated image samples
            if epoch % sample_interval == 0:
                self.sample_images(epoch)
                self.discriminator.save(
                    self.model_dir + "/" + "discriminator.h5")
                self.generator.save(self.model_dir + "/" + "generator.h5")
                self.combined.save(self.model_dir + "/" + "combined.h5")

    def sample_images(self, epoch):
        r, c = 1, self.num_classes
        noise = np.random.normal(0, 1, (r * c, 100))
        sampled_labels = np.arange(0, self.num_classes).reshape(-1, 1)

        gen_imgs = self.generator.predict([noise, sampled_labels])

        # Rescale images 0 - 1
        gen_imgs = 0.5 * gen_imgs + 0.5

        upper_limit = np.vectorize(lambda x: 1 if x > 1 else x)
        under_limit = np.vectorize(lambda x: 0 if x < 0 else x)

        gen_imgs = upper_limit(gen_imgs)
        gen_imgs = under_limit(gen_imgs)

        # plt.imshow(gen_imgs[1, :, :, 0], cmap='gray')
        # plt.show()

        fig, axs = plt.subplots(r, c)
        cnt = 0
        for i in range(r):
            for j in range(c):
                if(r == 1):
                    axs_i_j = axs[j]
                else:
                    axs_i_j = axs[i, j]
                axs_i_j.imshow(gen_imgs[cnt])
                axs_i_j.set_title(
                    "%s" % self.categories[sampled_labels[cnt][0]])
                axs_i_j.axis('off')
                cnt += 1
        fig.savefig("images/%d.png" % epoch)
        plt.close()

    def _load_image_to_array(self, input_dir):

        x = []
        y = []
        categories = []

        # ./data/train または ./data/test 以下のカテゴリの取得
        for dir_name in os.listdir(input_dir):
            if dir_name == ".DS_Store":
                continue
            categories.append(dir_name)

        for idx, category in enumerate(categories):
            category_dir = input_dir + "/" + category
            print("---category dir:", category_dir)

            for file in os.listdir(category_dir):
                if file != ".DS_Store" and file != ".keep":
                    filepath = category_dir + "/" + file
                    image = self.preprocess_image(filepath)
                    # 出来上がった配列をimage_listに追加。
                    x.append(image)
                    # 配列label_listに正解ラベルを追加(0,1,2...)
                    y.append(idx)

        # kerasに渡すためにnumpy配列に変換。
        x = np.array(x)

        # ラベルの配列をone hotラベル配列に変更
        # 0 -> [1,0,0,0], 1 -> [0,1,0,0] という感じ。
        if(len(y) > 0):
            y = to_categorical(y)

        return (x, y, categories)

    def prepare_train_data(self):

        # 学習用のデータを作る.
        self.x_train = []
        self.y_train = []
        self.x_test = []
        self.y_test = []
        self.categories = []

        (self.x_train, self.y_train,
         self.categories) = self._load_image_to_array("data/train")

        self.num_classes = self.y_train.shape[1]

        print("prepare: self.num_classes:", self.num_classes)

        # if subtract_pixel_mean:
        #    self.x_train_mean = np.mean(self.x_train, axis=0)
        #    self.x_train -= self.x_train_mean
        #    self.x_test -= self.x_train_mean

        print('x_train shape:', self.x_train.shape)
        print('y_train shape:', self.y_train.shape)

    def preprocess_image(self, filepath):
        # 画像を48 x 48(pixel設定可) x channel のnp_arrayに変換

        image = Image.open(filepath)
        image = np.array(image.resize((self.img_rows, self.img_cols)))
        image = image.reshape(self.img_rows, self.img_cols, self.channels)

        print("preprocess, image.shape:", image.shape)

        return image

    def load(self, filepath):
        self.model = load_model(filepath)


if __name__ == '__main__':
    cgan = FruitCondDCGanModel(image_size=48)
    cgan.train(epochs=1000, batch_size=32, sample_interval=20)
