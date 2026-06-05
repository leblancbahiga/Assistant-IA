# test case file for LSTM model in Keras

from __future__ import print_function

import json
import numpy as np
from keras.models import Sequential, model_from_json
from keras import layers, optimizers, metrics

# ─── Paramètres ───
num_features = 1   # nombre de features dans le dataset
timesteps = 32     # longueur de la séquence temporelle (tronquée ou paddée)
num_classes = 1    # nombre de neurones en sortie

# ─── Construction du modèle LSTM ───
lstm_model = Sequential()
lstm_model.add(layers.LSTM(32, return_sequences=True,
                           input_shape=(timesteps, num_features)))
lstm_model.add(layers.Dropout(0.5))
lstm_model.add(layers.Dense(num_classes))

# ─── Compilation ───
optimizer = optimizers.Adam(learning_rate=0.001)
lstm_model.compile(loss='mse', optimizer=optimizer)

# ─── Entraînement (à décommenter avec tes vraies données) ───
# history = lstm_model.fit(X_train, y_train, epochs=50,
#                          batch_size=32, validation_split=0.2)

# ─── Évaluation ───
lstm_model.load_weights('lstm.h5')
# predictions = lstm_model.predict(X_test)
# rmse = np.sqrt(metrics.mean_squared_error(y_pred, y_true))
# print("Root Mean Squared Error (RMSE) evaluation metric is:", rmse)

# ─── Sauvegarde du modèle ───
lstm_model_json = lstm_model.to_json()
with open("lstm.json", "w") as outfile:
    json.dump(lstm_model_json, outfile)

# ─── Rechargement depuis JSON ───
# lstm_model = model_from_json(lstm_model.to_json())
# lstm_model.load_weights('lstm.h5')
