# -*- coding: utf-8 -*-
"""MGKN.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/11l9leGFgBcsaTIpSFjxUSjDBhQCnI1Ou
"""


import torch
import numpy as np
import torch.nn.functional as F
import torch.nn as nn
import matplotlib.pyplot as plt
from utilities import *
from torch_geometric.data import Data, DataLoader
from torch_geometric.nn import NNConv
from timeit import default_timer
from scipy.ndimage.filters import gaussian_filter

torch.manual_seed(0)
np.random.seed(0)

data = np.load('chdata1.npy')

plt.imshow(data[0, :, :, 0])

plt.imshow(data[5, :, :, 0])

########################################################################
#
#  Hyperparameters
#
########################################################################

s = 64 #the grid size
r = 5 #downsample
s0 = int(((s - 1)/r) + 1) #grid size after downsample
n = s**2 # number of nodes
k = 1 # graph sampled per training pairs

m = [400, 100, 25] # number of nodes sampled for each layers
radius_inner = [0.25, 0.5, 1] # r_{l,l}
radius_inter = [0.125, 0.25] # r_{l,l+1} = r_{l+1,l}

level = len(m) # number of levels L
print('resolution', s)

splits = n // m[0]
if splits * m[0] < n:
    splits = splits + 1


ntrain = 900 # number of training pairs N
ntest = 100 # number of testing pairs

batch_size = 1 #train
batch_size2 = 1 #test
width = 64  #d_v
ker_width = 1024 #1024
depth = 4  #T
edge_features = 6
theta_d = 1
node_features = 6 #1 + theta_d


epochs = 200
learning_rate = 0.0001
scheduler_step = 10
scheduler_gamma = 0.80


path = 'multipole_burgersR10_s'+str(s)+'_ntrain'+str(ntrain)+'_kerwidth'+str(ker_width)
path_model = "./"
path_train_err = './train.txt'
path_test_err = './test.txt'
path_image = './'

trainu = data[:ntrain, :, :, 1]
trainu = trainu.astype(np.float32)
traina = data[:ntrain, :, :, 0]
traina = traina.astype(np.float32)


plt.imshow(traina[1])

plt.imshow(smooth_a[0])

########################################################################
#
#  Read the data
#
########################################################################


#reader = MatReader(TRAIN_PATH)
#train_a = reader.read_field('a')[:ntrain,::r].reshape(ntrain,-1)
#print(train_a.shape)
#train_u = reader.read_field('u')[:ntrain,::r].reshape(ntrain,-1)
#print(train_u.shape)

train_u = torch.from_numpy(data[:ntrain, :, :, 1].reshape(ntrain, -1))
train_a = torch.from_numpy(data[:ntrain, :, :, 0].reshape(ntrain, -1))

train_a_smooth = torch.from_numpy(gaussian_filter(train_a, sigma=2).reshape(ntrain, -1))
train_a_gradx = torch.from_numpy(np.gradient(train_a_smooth, axis = 0).reshape(ntrain, -1))
train_a_grady = torch.from_numpy(np.gradient(train_a_smooth, axis = 1).reshape(ntrain, -1))

test_u = torch.from_numpy(data[ntrain:ntrain+ntest, :, :, 1].reshape(ntest, -1))
test_a = torch.from_numpy(data[ntrain:ntrain+ntest, :, :, 0].reshape(ntest, -1))

test_a_smooth = torch.from_numpy(gaussian_filter(test_a, sigma=2).reshape(ntest, -1))
test_a_gradx = torch.from_numpy(np.gradient(test_a_smooth, axis = 0).reshape(ntest, -1))
test_a_grady = torch.from_numpy(np.gradient(test_a_smooth, axis = 1).reshape(ntest, -1))

#reader.load_file(TEST_PATH)
#test_a = reader.read_field('a')[-ntest:,::r].reshape(ntest,-1)
#test_u = reader.read_field('u')[-ntest:,::r].reshape(ntest,-1)


a_normalizer = GaussianNormalizer(train_a)
train_a = a_normalizer.encode(train_a)
test_a = a_normalizer.encode(test_a)

u_normalizer = UnitGaussianNormalizer(train_u)
train_u = u_normalizer.encode(train_u)
#test_u = u_normalizer.encode(test_u)

as_normalizer = GaussianNormalizer(train_a_smooth)
train_a_smooth = as_normalizer.encode(train_a_smooth)
test_a_smooth = as_normalizer.encode(test_a_smooth)
agx_normalizer = GaussianNormalizer(train_a_gradx)
train_a_gradx = agx_normalizer.encode(train_a_gradx)
test_a_gradx = agx_normalizer.encode(test_a_gradx)
agy_normalizer = GaussianNormalizer(train_a_grady)
train_a_grady = agy_normalizer.encode(train_a_grady)
test_a_grady = agy_normalizer.encode(test_a_grady)

train_theta = train_a.reshape(ntrain*64,s,1)
test_theta = test_a.reshape(ntest*64,s,1)

########################################################################
#
#  Construct Graphs
#
########################################################################


meshgenerator = RandomMultiMeshGenerator([[0,1],[0,1]],[s,s], level=level, sample_sizes=m)
data_train = []
for j in range(ntrain):
    for i in range(k):
        idx, idx_all = meshgenerator.sample()
        grid, grid_all = meshgenerator.get_grid()
        edge_index, edge_index_down, edge_index_up = meshgenerator.ball_connectivity(radius_inner, radius_inter)
        edge_index_range, edge_index_down_range, edge_index_up_range = meshgenerator.get_edge_index_range()
        edge_attr, edge_attr_down, edge_attr_up = meshgenerator.attributes(theta=train_a[j,:])
        x = torch.cat([grid_all, train_a[j, idx_all].reshape(-1, 1),
                       train_a_smooth[j, idx_all].reshape(-1, 1),
                       train_a_gradx[j, idx_all].reshape(-1, 1),
                       train_a_grady[j, idx_all].reshape(-1, 1)
                       ], dim=1).float()
        data_train.append(Data(x=x, y=train_u[j, idx[0]],
                              edge_index_mid=edge_index, edge_index_down=edge_index_down, edge_index_up=edge_index_up,
                              edge_index_range=edge_index_range, edge_index_down_range=edge_index_down_range, edge_index_up_range=edge_index_up_range,
                              edge_attr_mid=edge_attr, edge_attr_down=edge_attr_down, edge_attr_up=edge_attr_up,
                              sample_idx=idx[0]))

print(x.shape, edge_index.shape, edge_index_down.shape,  edge_index_range.shape, edge_attr.shape, edge_attr_down.shape)

train_loader = DataLoader(data_train, batch_size=batch_size, shuffle=True)


meshgenerator = RandomMultiMeshSplitter([[0,1],[0,1]],[s,s], level=level, sample_sizes=m)
data_test = []
test_theta = torch.stack([test_a, test_a_smooth, test_a_gradx, test_a_grady], dim=2).float()
for j in range(ntest):
    data = meshgenerator.splitter(radius_inner, radius_inter, test_a[j,:], test_theta[j,:,:])
    test_loader = DataLoader(data, batch_size=batch_size2, shuffle=False)
    data_test.append(test_loader)


t2 = default_timer()

########################################################################
#
#  The neural networks architecture
#
########################################################################

class MKGN(torch.nn.Module):
    def __init__(self, width, ker_width, depth, ker_in, points, level, in_width=1, out_width=1):
        super(MKGN, self).__init__()
        self.depth = depth
        self.width = width
        self.level = level

        index = 0
        self.points = [0]
        for point in points:
            index = index + point
            self.points.append(index)
        print(level, self.points)

        self.points_total = np.sum(points)

        # in (P)
        self.fc_in = torch.nn.Linear(in_width, width)

        # K12 K23 K34 ...
        self.conv_down_list = []
        for l in range(1, level):
            ker_width_l = ker_width // (2 ** l)
            kernel_l = DenseNet([ker_in, ker_width_l, width ** 2], torch.nn.ReLU)
            self.conv_down_list.append(NNConv(width, width, kernel_l, aggr='mean', root_weight=False, bias=False))
        self.conv_down_list = torch.nn.ModuleList(self.conv_down_list)

        # K11 K22 K33
        self.conv_list = []
        for l in range(level):
            ker_width_l = ker_width // (2 ** l)
            kernel_l = DenseNet([ker_in, ker_width_l, ker_width_l, width ** 2], torch.nn.ReLU)
            self.conv_list.append(NNConv(width, width, kernel_l, aggr='mean', root_weight=True, bias=False))
        self.conv_list = torch.nn.ModuleList(self.conv_list)

        # K21 K32 K43
        self.conv_up_list = []
        for l in range(1, level):
            ker_width_l = ker_width // (2 ** l)
            kernel_l = DenseNet([ker_in, ker_width_l, width ** 2], torch.nn.ReLU)
            self.conv_up_list.append(NNConv(width, width, kernel_l, aggr='mean', root_weight=False, bias=False))
        self.conv_up_list = torch.nn.ModuleList(self.conv_up_list)

        # out (Q)
        self.fc_out1 = torch.nn.Linear(width, ker_width)
        self.fc_out2 = torch.nn.Linear(ker_width, 1)


    def forward(self, data):
        edge_index_down, edge_attr_down, range_down = data.edge_index_down, data.edge_attr_down, data.edge_index_down_range
        edge_index_mid, edge_attr_mid, range_mid = data.edge_index_mid, data.edge_attr_mid, data.edge_index_range
        edge_index_up, edge_attr_up, range_up = data.edge_index_up, data.edge_attr_up, data.edge_index_up_range

        x = self.fc_in(data.x)

        for t in range(self.depth):
            #downward
            for l in range(self.level-1):
                x = x + self.conv_down_list[l](x, edge_index_down[:,range_down[l,0]:range_down[l,1]], edge_attr_down[range_down[l,0]:range_down[l,1],:])
                x = F.relu(x)

            #upward
            for l in reversed(range(self.level)):
                x[self.points[l]:self.points[l+1]] = self.conv_list[l](x[self.points[l]:self.points[l+1]].clone(),
                                                                       edge_index_mid[:,range_mid[l,0]:range_mid[l,1]]-self.points[l],
                                                                        edge_attr_mid[range_mid[l,0]:range_mid[l,1],:])

                if l > 0:
                    x = x + self.conv_up_list[l-1](x, edge_index_up[:,range_up[l-1,0]:range_up[l-1,1]], edge_attr_up[range_up[l-1,0]:range_up[l-1,1],:])
                    x = F.relu(x)

        x = F.relu(self.fc_out1(x[:self.points[1]]))
        x = self.fc_out2(x)
        return x

########################################################################
#
#  Training
#
########################################################################


#print('preprocessing finished, time used:', t2-t1)
device = torch.device('cuda')

# print('use pre-train model')
model = torch.load('/content/gdrive/MyDrive/CHdata/models/10.pt')

#model = MKGN(width=width, ker_width=ker_width, depth=depth, ker_in=edge_features,
 #            points=m, level=level, in_width=node_features, out_width=1).cuda()

optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=5e-4)
scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=scheduler_step, gamma=scheduler_gamma)

myloss = LpLoss(size_average=False)
ttrain = np.zeros((epochs, ))
ttest = np.zeros((epochs,))

for ep in range(epochs):
    t1 = default_timer()
    train_mse = 0.0
    train_l2 = 0.0
    model.train()
    u_normalizer.cuda()
    for batch in train_loader:
        batch = batch.to(device)

        optimizer.zero_grad()
        out = model(batch)
        mse = F.mse_loss(out.view(-1, 1), batch.y.view(-1,1))
        # mse.backward()

        loss = torch.norm(out.view(-1) - batch.y.view(-1),1)
        # loss.backward()

        l2 = myloss(
            u_normalizer.decode(out.view(batch_size, -1), sample_idx=batch.sample_idx.view(batch_size, -1)),
            u_normalizer.decode(batch.y.view(batch_size, -1), sample_idx=batch.sample_idx.view(batch_size, -1)))
        l2.backward()

        optimizer.step()
        train_mse += mse.item()
        train_l2 += l2.item()

    scheduler.step()
    t2 = default_timer()
    ttrain[ep] = train_l2 / (ntrain * k)
    if ep%10 == 0:
      torch.save(model, path_model+str(ep)+'.pt')

    print(ep, t2 - t1, train_mse / len(train_loader), train_l2 / (ntrain * k))

torch.save(model, path_model)


########################################################################
#
#  Testing
#
########################################################################

ep = epochs - 1
#ttest = np.zeros(epochs)
myloss = LpLoss(size_average=False)
model.eval()
test_l2_all = 0.0
test_l2_split = 0.0
u_normalizer.cpu()
with torch.no_grad():
    t1 = default_timer()
    for i, test_loader in enumerate(data_test):
        out_list = []
        sample_idx_list = []
        test_l2_split = 0.0
        for data in test_loader:
            data = data.to(device)
            out_split = model(data).cpu().detach()
            assert len(out_split) == len(data.sample_idx)
            out_split = u_normalizer.decode(out_split.view(batch_size2, -1),
                                            sample_idx=data.sample_idx.view(batch_size2, -1))
            test_l2_split += myloss(out_split, test_u[i, data.sample_idx].view(batch_size2, -1)).item()

            out_list.append(out_split.float())
            sample_idx_list.append(data.sample_idx.float())



        out = meshgenerator.assembler(out_list, sample_idx_list)
        l2 = myloss(out.view(1, -1), test_u[i].view(batch_size2, -1)).item()
        test_l2_all += l2
        print('test i =',i, l2, test_l2_split / len(test_loader))


    t2 = default_timer()
    print(ep, t2 - t1, test_l2_all / ntest)
    ttest[ep] = test_l2_all / ntest


np.savetxt(path_train_err, ttrain)
np.savetxt(path_test_err, ttest)

torch.save(model, './model.pt')

#model = torch.load('/content/gdrive/MyDrive/CHdata/models.pt')

